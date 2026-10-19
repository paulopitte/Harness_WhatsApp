"""Testes de Integração da User Story 1: Idempotência, Debounce, Claim Concorrente e Fluxo Ponta a Ponta (T017).

Valida SC-001, SC-002, SC-003 e SC-004:
1. Descarte silencioso de `provider_message_id` duplicado (100%).
2. Agrupamento de rajada de 3 mensagens em 1 único item na fila com concatenação de texto (Debounce).
3. Claim concorrente: múltiplos workers disputando o mesmo item sem duplicação.
4. Fluxo HTTP POST `/webhook` -> Quarentena Edge DLQ -> Fila -> `EchoCognitionEngine` -> `ConsoleOutboundProvider` -> `done`.
"""

import asyncio

import httpx
import pytest

from harness.cognition.echo_engine import EchoCognitionEngine
from harness.domain.message import NormalizedTextMessage
from harness.domain.value_objects import QueueStatus
from harness.edge.resilience import InMemoryQuarantineRepository
from harness.edge.webhook import create_webhook_app
from harness.ingress.postgres_queue import InMemoryQueueAdapter
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.outbound.sender import OutboundSender
from harness.settings import HarnessSettings
from harness.workers.pipeline import ProcessQueueItemPipeline
from scripts.send_fake_msg import build_meta_payload


async def test_debounce_concatenates_burst_and_idempotency_discards_duplicates() -> None:
    queue = InMemoryQueueAdapter(max_retries=3)

    msg1 = NormalizedTextMessage(
        provider_message_id="wamid.1",
        thread_id="wa:5511999998888",
        sender_phone="5511999998888",
        text_content="Oi",
    )
    msg2 = NormalizedTextMessage(
        provider_message_id="wamid.2",
        thread_id="wa:5511999998888",
        sender_phone="5511999998888",
        text_content="Tudo bem?",
    )
    msg3 = NormalizedTextMessage(
        provider_message_id="wamid.3",
        thread_id="wa:5511999998888",
        sender_phone="5511999998888",
        text_content="Qual o valor do plano?",
    )

    id1 = await queue.enqueue_with_debounce(msg1, debounce_seconds=0.05)
    # Duplicata exata de msg1 deve retornar None (FR-005 / SC-002)
    dup_id = await queue.enqueue_with_debounce(msg1, debounce_seconds=0.05)
    assert dup_id is None

    id2 = await queue.enqueue_with_debounce(msg2, debounce_seconds=0.05)
    id3 = await queue.enqueue_with_debounce(msg3, debounce_seconds=0.05)

    # Todas as 3 mensagens da rajada devem ter atualizado o MESMO QueueItem (FR-006 / SC-003)
    assert id1 == id2 == id3

    # Antes de vencer o scheduled_for, nenhum worker consegue fazer claim
    early_claim = await queue.claim_next_ready("worker-1")
    assert early_claim is None

    # Aguarda a janela de debounce expirar
    await asyncio.sleep(0.07)

    # Disputa concorrente entre 4 workers simultâneos (FR-008): exatamente 1 deve obter o lock
    claims = await asyncio.gather(
        queue.claim_next_ready("worker-1"),
        queue.claim_next_ready("worker-2"),
        queue.claim_next_ready("worker-3"),
        queue.claim_next_ready("worker-4"),
    )
    non_null_claims = [c for c in claims if c is not None]
    assert len(non_null_claims) == 1

    claimed = non_null_claims[0]
    assert claimed.status == QueueStatus.PROCESSING
    assert claimed.concatenated_text == "Oi\nTudo bem?\nQual o valor do plano?"
    assert claimed.provider_message_ids == ["wamid.1", "wamid.2", "wamid.3"]


@pytest.mark.asyncio
async def test_end_to_end_webhook_to_worker_echo_and_quarantine() -> None:
    settings = HarnessSettings.load("configs/harness.yaml")
    settings.queue.debounce_seconds = 0.01
    settings.edge.verify_signature = False

    queue = InMemoryQueueAdapter(max_retries=3)
    quarantine = InMemoryQuarantineRepository()
    console_provider = ConsoleOutboundProvider()
    outbound_sender = OutboundSender(console_provider)
    cognition = EchoCognitionEngine()

    pipeline = ProcessQueueItemPipeline(
        queue_consumer=queue,
        cognition_engine=cognition,
        outbound_sender=outbound_sender,
    )

    app = create_webhook_app(
        settings=settings,
        queue_enqueuer=queue,
        quarantine_repo=quarantine,
        outbound_sender=outbound_sender,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Envia payload corrompido -> deve cair na Quarentena (Edge DLQ) e retornar 200 OK
        corrupt_resp = await client.post("/webhook", content=b'{"bad_payload": 123}')
        assert corrupt_resp.status_code == 200
        assert corrupt_resp.json()["disposition"] == "quarantined"
        assert len(quarantine.entries) == 1

        # 2. Envia rajada de 2 mensagens válidas via HTTP POST /webhook
        p1 = build_meta_payload("5511999998888", "Olá", message_id="wamid.e2e.1")
        p2 = build_meta_payload("5511999998888", "Preciso de ajuda", message_id="wamid.e2e.2")

        r1 = await client.post("/webhook", json=p1)
        r2 = await client.post("/webhook", json=p2)
        assert r1.status_code == 200
        assert r2.status_code == 200

    await asyncio.sleep(0.03)

    # 3. Worker consome a fila, chama EchoCognitionEngine, envia no ConsoleOutboundProvider e marca DONE
    processed = await pipeline.process_next("worker-e2e")
    assert processed is not None

    stats = await queue.get_stats()
    assert stats.done == 1
    assert stats.pending == 0
    assert len(console_provider.sent_messages) == 1
    recipient, sent_text = console_provider.sent_messages[0]
    assert recipient == "5511999998888"
    assert "Recebi (2 msg): Olá | Preciso de ajuda" in sent_text

