"""Teste de Carga e Concorrência da Harness (`tests/load/test_burst_concurrency.py` — SC-002, SC-003, SC-004, T049).

Equivalente no C#/.NET: Teste de estresse com `Parallel.ForEachAsync` / `Task.WhenAll` validando:
1. Cenário A (Rajada com Debounce): 50 mensagens disparadas concorrentemente por 10 clientes (5 mensagens
   seguidas por telefone) -> fundidas atomicamente em 10 itens de fila consolidados e consumidas por
   4 workers paralelos sem duplicidade.
2. Cenário B (Alta Concorrência de Workers): 50 clientes distintos disparando 50 mensagens simultâneas
   consumidas por 4 workers concorrentes (`worker-1` a `worker-4`), garantindo `SKIP LOCKED` sem condição
   de corrida (exatamente 50 envios únicos no Outbound e `stats.done == 50`).
"""

import asyncio

import pytest

from harness.app import build_container
from harness.domain.message import NormalizedTextMessage
from harness.domain.value_objects import MediaType, PhoneNumber, ThreadId
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.settings import CognitionConfig, HarnessSettings


def _make_msg(phone_str: str, msg_idx: int, text: str) -> NormalizedTextMessage:
    phone = PhoneNumber(phone_str)
    return NormalizedTextMessage(
        provider_message_id=f"wamid.load.{phone_str}.{msg_idx}",
        thread_id=str(ThreadId.from_phone(phone)),
        sender_phone=str(phone),
        text_content=text,
        original_media_type=MediaType.TEXT,
    )


async def _drain_with_worker(container: object, worker_name: str) -> int:
    """Loop de um worker individual consumindo itens até a fila esvaziar."""
    from harness.app import HarnessContainer

    assert isinstance(container, HarnessContainer)
    processed = 0
    while True:
        item = await container.worker_pipeline.process_next(worker_name)
        if item is None:
            break
        processed += 1
        # Cede controle ao event loop para simular intercalação real entre os 4 workers
        await asyncio.sleep(0.001)
    return processed


@pytest.mark.asyncio
async def test_burst_50_messages_across_10_threads_coalesced_and_consumed_by_4_workers() -> None:
    """Dispara 50 mensagens (10 threads x 5 mensagens em rajada) e processa com 4 workers concorrentes."""
    settings = HarnessSettings(
        harness_env="test",
        cognition=CognitionConfig(agent_mode="langgraph"),
    )
    container = await build_container(settings, force_in_memory=True)
    assert isinstance(container.outbound_provider, ConsoleOutboundProvider)

    # 10 clientes enviando 5 mensagens picadas cada um (total = 50 chamadas concorrentes de enqueue)
    burst_messages: list[NormalizedTextMessage] = []
    for client_idx in range(10):
        phone = f"55119800000{client_idx:02d}"
        for part_idx in range(1, 6):
            burst_messages.append(
                _make_msg(phone, part_idx, f"Parte {part_idx} do cliente {client_idx}")
            )

    # Enfileira todas as 50 mensagens concorrentemente com debounce=0.0s (já prontas para claim)
    await asyncio.gather(
        *(
            container.queue_enqueuer.enqueue_with_debounce(m, debounce_seconds=0.0)
            for m in burst_messages
        )
    )

    stats_before = await container.queue_consumer.get_stats()
    # 50 mensagens de 10 clientes devem ter sido consolidadas em exatamente 10 itens pendentes!
    assert stats_before.pending == 10

    # 4 workers concorrentes drenam a fila simultaneamente
    counts = await asyncio.gather(
        _drain_with_worker(container, "worker-1"),
        _drain_with_worker(container, "worker-2"),
        _drain_with_worker(container, "worker-3"),
        _drain_with_worker(container, "worker-4"),
    )

    assert sum(counts) == 10
    stats_after = await container.queue_consumer.get_stats()
    assert stats_after.pending == 0
    assert stats_after.processing == 0
    assert stats_after.dead == 0
    assert stats_after.done == 10

    # Exatamente 10 respostas enviadas no Outbound (1 por cliente, contendo todas as 5 partes concatenadas)
    sent = container.outbound_provider.sent_messages
    assert len(sent) == 10
    recipients = {phone for phone, _ in sent}
    assert len(recipients) == 10
    for _, reply_text in sent:
        for part_idx in range(1, 6):
            assert f"Parte {part_idx}" in reply_text


@pytest.mark.asyncio
async def test_50_distinct_threads_processed_in_parallel_by_4_workers_without_race_condition() -> None:
    """Dispara 50 mensagens de 50 telefones distintos e valida que 4 workers concorrentes processam
    exatamente 50 itens sem duplicidade (SC-004).
    """
    settings = HarnessSettings(
        harness_env="test",
        cognition=CognitionConfig(agent_mode="echo"),
    )
    container = await build_container(settings, force_in_memory=True)
    assert isinstance(container.outbound_provider, ConsoleOutboundProvider)

    messages = [
        _make_msg(f"55119700000{idx:02d}", 1, f"Mensagem concorrente #{idx}")
        for idx in range(50)
    ]

    await asyncio.gather(
        *(
            container.queue_enqueuer.enqueue_with_debounce(m, debounce_seconds=0.0)
            for m in messages
        )
    )

    stats_before = await container.queue_consumer.get_stats()
    assert stats_before.pending == 50

    counts = await asyncio.gather(
        _drain_with_worker(container, "worker-1"),
        _drain_with_worker(container, "worker-2"),
        _drain_with_worker(container, "worker-3"),
        _drain_with_worker(container, "worker-4"),
    )

    # Soma dos itens processados pelos 4 workers deve ser exatamente 50
    assert sum(counts) == 50

    stats_after = await container.queue_consumer.get_stats()
    assert stats_after.pending == 0
    assert stats_after.processing == 0
    assert stats_after.dead == 0
    assert stats_after.done == 50

    sent = container.outbound_provider.sent_messages
    assert len(sent) == 50
    unique_recipients = {phone for phone, _ in sent}
    assert len(unique_recipients) == 50

