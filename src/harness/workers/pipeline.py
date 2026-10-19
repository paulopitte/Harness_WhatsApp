"""Pipeline de Orquestração do Worker (`ProcessQueueItemPipeline` — T024, T047).

Equivalente no C#/.NET: Application Command Handler que coordena:
1. Claim atômico da fila (`QueueConsumerProtocol.claim_next_ready`).
2. Verificação de Handoff Humano (`ThreadMode.BOT` vs `HUMAN` / `PAUSED` — FR-015):
   - Se a thread estiver em modo `human` ou `paused`, apenas registra a mensagem no histórico
     da conversa (`threads_repo.append_message`) para o atendente humano ler e marca o item como `done`,
     sem acionar a LLM nem o Outbound.
3. Chamada ao motor de cognição (`CognitionEngineProtocol.generate_reply`).
4. Envio confirmado pelo Outbound (`OutboundSender.deliver`).
5. Marcação como `done` (sucesso) ou `mark_failed_or_dead` (retry com backoff / Business DLQ).
"""

from collections.abc import Callable

from harness.domain.ports import CognitionEngineProtocol, QueueConsumerProtocol
from harness.domain.queue import QueueItem
from harness.domain.value_objects import ThreadId, ThreadMode
from harness.outbound.sender import OutboundSender
from harness.persistence.threads_repo import ThreadsRepositoryProtocol


class ProcessQueueItemPipeline:
    """Caso de uso central do Worker assíncrono."""

    def __init__(
        self,
        queue_consumer: QueueConsumerProtocol,
        cognition_engine: CognitionEngineProtocol,
        outbound_sender: OutboundSender,
        *,
        threads_repo: ThreadsRepositoryProtocol | None = None,
        retry_base_backoff_seconds: float = 5.0,
        thread_mode_resolver: Callable[[str], ThreadMode] | None = None,
    ) -> None:
        self._queue = queue_consumer
        self._cognition = cognition_engine
        self._outbound = outbound_sender
        self._threads_repo = threads_repo
        self._backoff_seconds = retry_base_backoff_seconds
        self._thread_mode_resolver = thread_mode_resolver

    async def _resolve_current_mode(self, thread_id: str) -> ThreadMode:
        if self._thread_mode_resolver is not None:
            return self._thread_mode_resolver(thread_id)
        if self._threads_repo is not None:
            thread = await self._threads_repo.get_or_create_thread(thread_id)
            return thread.mode
        return ThreadMode.BOT

    async def process_next(self, worker_id: str = "worker-1") -> QueueItem | None:
        """Puxa o próximo item pronto da fila e executa o ciclo transacional completo."""
        item = await self._queue.claim_next_ready(worker_id)
        if item is None:
            return None

        # Verifica se a thread está em Handoff Humano (`human`) ou `paused` (FR-015, T047)
        current_mode = await self._resolve_current_mode(item.thread_id)
        if current_mode != ThreadMode.BOT:
            if self._threads_repo is not None:
                await self._threads_repo.append_message(
                    item.thread_id,
                    "user",
                    item.concatenated_text,
                )
            await self._queue.mark_done(item.id)
            return item

        try:
            thread_vo = ThreadId(item.thread_id)
            reply_text = await self._cognition.generate_reply(
                thread_id=thread_vo,
                user_text=item.concatenated_text,
                queue_item_id=item.id,
            )
            await self._outbound.deliver(
                recipient_phone=item.phone_number,
                text=reply_text,
            )
            await self._queue.mark_done(item.id)
            return item
        except Exception as exc:
            updated = await self._queue.mark_failed_or_dead(
                item_id=item.id,
                error_message=f"{type(exc).__name__}: {exc}",
                backoff_seconds=self._backoff_seconds,
            )
            return updated
