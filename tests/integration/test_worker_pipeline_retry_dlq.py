"""Testes de Integração do Pipeline do Worker: Retries Exponenciais, Business DLQ (`dead`) e Meta Outbound (`T029`)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest

from harness.cognition.echo_engine import EchoCognitionEngine
from harness.domain.exceptions import OutboundDeliveryError
from harness.domain.message import NormalizedTextMessage
from harness.domain.value_objects import MediaType, PhoneNumber, QueueStatus, ThreadId
from harness.ingress.postgres_queue import InMemoryQueueAdapter
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.outbound.providers.meta import MetaOutboundProvider
from harness.outbound.sender import OutboundSender
from harness.workers.pipeline import ProcessQueueItemPipeline


class FlakyCognitionEngine:
    """Motor de cognição que simula falha nas N primeiras chamadas para testar retry e DLQ."""

    def __init__(self, fail_times: int = 99) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def generate_reply(
        self,
        thread_id: ThreadId,
        user_text: str,
        queue_item_id: UUID | None = None,
    ) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"Timeout simulado do provedor LLM na tentativa #{self.calls}")
        return f"Resposta recuperada na tentativa #{self.calls}: {user_text}"


def _make_sample_message(msg_id: str = "wamid.dlq.1", text: str = "Olá, preciso de suporte") -> NormalizedTextMessage:
    phone = PhoneNumber("5511966665555")
    return NormalizedTextMessage(
        provider_message_id=msg_id,
        thread_id=ThreadId.from_phone(phone),
        phone_number=phone,
        text_content=text,
        original_media_type=MediaType.TEXT,
    )


@pytest.mark.asyncio
async def test_worker_pipeline_retries_and_transitions_to_business_dlq_dead() -> None:
    """Valida que um item com falha persistente sofre retries (`attempts` 1..3) e vai para `dead` (Business DLQ),
    podendo ser reprocessado depois via `reprocess_dead_items()` (FR-008, FR-018, SC-005).
    """
    queue = InMemoryQueueAdapter(max_retries=3)
    flaky_engine = FlakyCognitionEngine(fail_times=3)
    console_provider = ConsoleOutboundProvider()
    sender = OutboundSender(console_provider, provider_name="console")

    pipeline = ProcessQueueItemPipeline(
        queue_consumer=queue,
        cognition_engine=flaky_engine,
        outbound_sender=sender,
        retry_base_backoff_seconds=0.01,
    )

    item_id = await queue.enqueue_with_debounce(_make_sample_message(), debounce_seconds=0.0)
    assert item_id is not None

    # Tentativa 1: falha -> volta para `pending` com `attempts = 1`
    res1 = await pipeline.process_next("worker-test")
    assert res1 is not None
    assert res1.attempts == 1
    assert res1.status == QueueStatus.PENDING
    assert "Timeout simulado" in (res1.last_error or "")

    # Força vencimento imediato do backoff para o teste não esperar relógio real
    queue._items[item_id] = queue._items[item_id].model_copy(
        update={"scheduled_for": datetime.now(UTC) - timedelta(seconds=1)}
    )

    # Tentativa 2: falha -> volta para `pending` com `attempts = 2`
    res2 = await pipeline.process_next("worker-test")
    assert res2 is not None
    assert res2.attempts == 2
    assert res2.status == QueueStatus.PENDING

    queue._items[item_id] = queue._items[item_id].model_copy(
        update={"scheduled_for": datetime.now(UTC) - timedelta(seconds=1)}
    )

    # Tentativa 3 (`attempts == max_retries`): falha -> movido para Business DLQ (`status = 'dead'`)
    res3 = await pipeline.process_next("worker-test")
    assert res3 is not None
    assert res3.attempts == 3
    assert res3.status == QueueStatus.DEAD

    stats_dead = await queue.get_stats()
    assert stats_dead.dead == 1
    assert stats_dead.pending == 0
    assert len(console_provider.sent_messages) == 0

    # Operação Admin (`POST /admin/dlq/reprocess`): move de `dead` para `pending` com `attempts = 0`
    reprocessed_count = await queue.reprocess_dead_items()
    assert reprocessed_count == 1

    # Na 4ª chamada ao `flaky_engine` (`fail_times=3`), o motor se recupera e conclui como `done`!
    res_recovered = await pipeline.process_next("worker-test")
    assert res_recovered is not None
    stats_done = await queue.get_stats()
    assert stats_done.done == 1
    assert stats_done.dead == 0
    assert len(console_provider.sent_messages) == 1
    assert "Resposta recuperada na tentativa #4" in console_provider.sent_messages[0][1]


@pytest.mark.asyncio
async def test_meta_outbound_provider_retries_on_503_and_succeeds() -> None:
    """Valida que `MetaOutboundProvider` faz retry automático em erro HTTP 503 da Meta e confirma entrega 200 OK."""
    attempts = 0

    def _mock_meta_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=503, json={"error": {"message": "Service temporarily unavailable"}})
        return httpx.Response(
            status_code=200,
            json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.out.123"}]},
        )

    transport = httpx.MockTransport(_mock_meta_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        provider = MetaOutboundProvider(
            access_token="EAABsbCS1iHgBO_fake_token",
            phone_number_id="10987654321",
            http_client=mock_client,
        )
        queue = InMemoryQueueAdapter(max_retries=3)
        await queue.enqueue_with_debounce(_make_sample_message("wamid.meta.1"), debounce_seconds=0.0)

        pipeline = ProcessQueueItemPipeline(
            queue_consumer=queue,
            cognition_engine=EchoCognitionEngine(),
            outbound_sender=OutboundSender(provider, provider_name="meta"),
        )
        processed = await pipeline.process_next("worker-meta")
        assert processed is not None
        assert attempts == 2
        stats = await queue.get_stats()
        assert stats.done == 1


@pytest.mark.asyncio
async def test_meta_outbound_provider_raises_on_401_unauthorized() -> None:
    """Garante que erro 401 de credencial inválida na Meta API lança `OutboundDeliveryError` imediatamente."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(status_code=401, json={"error": {"message": "Invalid OAuth access token"}})
    )
    async with httpx.AsyncClient(transport=transport) as mock_client:
        provider = MetaOutboundProvider(
            access_token="invalid_token",
            phone_number_id="10987654321",
            http_client=mock_client,
        )
        with pytest.raises(OutboundDeliveryError):
            await provider.send_text("5511966665555", "Teste")

