"""Composition Root (`app.py` — T026): Injeção de Dependências conectando Ports e Adapters.

Equivalente no C#/.NET: `Program.cs` (`builder.Services.AddSingleton<IQueue, PostgresQueueAdapter>()`).
Centraliza a montagem de todos os componentes sem espalhar acoplamento concreto pelo sistema (SOLID DIP).
"""

from dataclasses import dataclass

from harness.cognition.echo_engine import EchoCognitionEngine
from harness.domain.ports import (
    CognitionEngineProtocol,
    OutboundProviderProtocol,
    QueueConsumerProtocol,
    QueueEnqueuerProtocol,
)
from harness.edge.resilience import InMemoryQuarantineRepository, QuarantineRepositoryProtocol
from harness.ingress.database import DatabasePoolManager
from harness.ingress.postgres_queue import InMemoryQueueAdapter, PostgresQueueAdapter
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.outbound.sender import OutboundSender
from harness.settings import HarnessSettings, get_settings
from harness.workers.pipeline import ProcessQueueItemPipeline
from harness.workers.runner import WorkerRunner


@dataclass
class HarnessContainer:
    """Container de dependências instanciadas da aplicação."""

    settings: HarnessSettings
    db_manager: DatabasePoolManager | None
    queue_enqueuer: QueueEnqueuerProtocol
    queue_consumer: QueueConsumerProtocol
    quarantine_repo: QuarantineRepositoryProtocol
    cognition_engine: CognitionEngineProtocol
    outbound_provider: OutboundProviderProtocol
    outbound_sender: OutboundSender
    worker_pipeline: ProcessQueueItemPipeline
    worker_runner: WorkerRunner


async def build_container(
    settings: HarnessSettings | None = None,
    *,
    force_in_memory: bool = False,
) -> HarnessContainer:
    """Monta e conecta todas as portas e adaptadores de acordo com `HarnessSettings`."""
    cfg = settings or get_settings()

    db_manager: DatabasePoolManager | None = None
    if cfg.queue.provider == "postgres" and not force_in_memory:
        db_manager = DatabasePoolManager(cfg.database_url)
        pool = await db_manager.open()
        pg_adapter = PostgresQueueAdapter(pool, max_retries=cfg.queue.max_retries)
        queue_enqueuer: QueueEnqueuerProtocol = pg_adapter
        queue_consumer: QueueConsumerProtocol = pg_adapter
        quarantine_repo: QuarantineRepositoryProtocol = pg_adapter
    else:
        mem_adapter = InMemoryQueueAdapter(max_retries=cfg.queue.max_retries)
        queue_enqueuer = mem_adapter
        queue_consumer = mem_adapter
        quarantine_repo = InMemoryQuarantineRepository()

    # Provedor Outbound
    outbound_provider: OutboundProviderProtocol = ConsoleOutboundProvider()
    outbound_sender = OutboundSender(outbound_provider, provider_name=cfg.outbound.provider)

    # Motor de Cognição (Fase 3: EchoCognitionEngine; Fase 4+: LangGraphCognitionEngine)
    cognition_engine: CognitionEngineProtocol = EchoCognitionEngine()

    worker_pipeline = ProcessQueueItemPipeline(
        queue_consumer=queue_consumer,
        cognition_engine=cognition_engine,
        outbound_sender=outbound_sender,
        retry_base_backoff_seconds=cfg.queue.retry_base_backoff_seconds,
    )

    worker_runner = WorkerRunner(
        pipeline=worker_pipeline,
        concurrency=cfg.queue.worker_concurrency,
        poll_interval_seconds=cfg.queue.worker_poll_interval_seconds,
    )

    return HarnessContainer(
        settings=cfg,
        db_manager=db_manager,
        queue_enqueuer=queue_enqueuer,
        queue_consumer=queue_consumer,
        quarantine_repo=quarantine_repo,
        cognition_engine=cognition_engine,
        outbound_provider=outbound_provider,
        outbound_sender=outbound_sender,
        worker_pipeline=worker_pipeline,
        worker_runner=worker_runner,
    )

