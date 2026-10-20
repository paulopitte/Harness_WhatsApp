"""Composition Root (`app.py` — T026 / T030-T048): Injeção de Dependências conectando Ports e Adapters.

Equivalente no C#/.NET: `Program.cs` (`builder.Services.AddSingleton<IQueue, PostgresQueueAdapter>()`).
Centraliza a montagem de todos os componentes sem espalhar acoplamento concreto pelo sistema (SOLID DIP).
"""

from dataclasses import dataclass

from harness.cognition.echo_engine import EchoCognitionEngine
from harness.cognition.factory import ModelFactory
from harness.cognition.graph import LangGraphCognitionEngine
from harness.cognition.middlewares import (
    AuditRunMiddleware,
    ConversationMemoryMiddleware,
    InMemoryTokenBudgetStore,
    LatencyTrackingMiddleware,
    MiddlewarePipeline,
    PostgresTokenBudgetStore,
    TokenBudgetMiddleware,
    TokenBudgetStoreProtocol,
)
from harness.cognition.prompts.manager import PromptManager
from harness.cognition.retrievers.factory import VectorStoreFactory
from harness.domain.ports import (
    CognitionEngineProtocol,
    OutboundProviderProtocol,
    PromptProviderPort,
    QueueConsumerProtocol,
    QueueEnqueuerProtocol,
    RetrieverPort,
)
from harness.edge.media.router import EdgeMediaRouter
from harness.edge.media.transcribe import AudioTranscriber
from harness.edge.media.vision import ImageVisionDescriber
from harness.edge.rate_limit import (
    InMemoryRateLimiter,
    PostgresRateLimiter,
    RateLimiterProtocol,
)
from harness.edge.resilience import InMemoryQuarantineRepository, QuarantineRepositoryProtocol
from harness.ingress.database import DatabasePoolManager
from harness.ingress.postgres_queue import InMemoryQueueAdapter, PostgresQueueAdapter
from harness.ops.telemetry import configure_observability
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.outbound.providers.meta import MetaOutboundProvider
from harness.outbound.sender import OutboundSender
from harness.persistence.runs_repo import (
    InMemoryRunsRepository,
    PostgresRunsRepository,
    RunsQueryRepositoryProtocol,
)
from harness.persistence.threads_repo import (
    InMemoryThreadsRepository,
    PostgresThreadsRepository,
    ThreadsRepositoryProtocol,
)
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
    rate_limiter: RateLimiterProtocol
    media_router: EdgeMediaRouter
    threads_repo: ThreadsRepositoryProtocol
    retriever: RetrieverPort
    prompt_provider: PromptProviderPort
    token_budget_store: TokenBudgetStoreProtocol
    agent_run_repo: RunsQueryRepositoryProtocol
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
    configure_observability(cfg)

    db_manager: DatabasePoolManager | None = None
    pool = None
    if cfg.queue.provider == "postgres" and not force_in_memory:
        db_manager = DatabasePoolManager(cfg.database_url)
        pool = await db_manager.open()
        pg_adapter = PostgresQueueAdapter(pool, max_retries=cfg.queue.max_retries)
        queue_enqueuer: QueueEnqueuerProtocol = pg_adapter
        queue_consumer: QueueConsumerProtocol = pg_adapter
        quarantine_repo: QuarantineRepositoryProtocol = pg_adapter
        rate_limiter: RateLimiterProtocol = PostgresRateLimiter(
            pool,
            window_seconds=cfg.edge.rate_limit_window_seconds,
            max_messages=cfg.edge.rate_limit_max_messages,
        )
        threads_repo: ThreadsRepositoryProtocol = PostgresThreadsRepository(pool)
        token_budget_store: TokenBudgetStoreProtocol = PostgresTokenBudgetStore(pool)
        agent_run_repo: RunsQueryRepositoryProtocol = PostgresRunsRepository(pool)
    else:
        mem_adapter = InMemoryQueueAdapter(max_retries=cfg.queue.max_retries)
        queue_enqueuer = mem_adapter
        queue_consumer = mem_adapter
        mem_quarantine = InMemoryQuarantineRepository()
        quarantine_repo = mem_quarantine
        rate_limiter = InMemoryRateLimiter(
            window_seconds=cfg.edge.rate_limit_window_seconds,
            max_messages=cfg.edge.rate_limit_max_messages,
        )
        threads_repo = InMemoryThreadsRepository()
        token_budget_store = InMemoryTokenBudgetStore()
        agent_run_repo = InMemoryRunsRepository(quarantine_repo=mem_quarantine)

    # Roteador de Mídia na Borda (`text` | `audio` | `image` | `unsupported`)
    media_router = EdgeMediaRouter(
        media_config=cfg.edge.media,
        transcriber=AudioTranscriber(api_key=cfg.google_api_key, model_name=cfg.cognition.llm.model),
        vision_describer=ImageVisionDescriber(
            api_key=cfg.google_api_key,
            model_name=cfg.cognition.llm.model,
        ),
    )

    # Busca Vetorial RAG Agnóstica (`postgres` | `qdrant` | `in_memory`)
    rag_cfg = cfg.rag.model_copy(
        update={"provider": "in_memory" if force_in_memory else cfg.rag.provider}
    )
    retriever = VectorStoreFactory.create(rag_cfg, settings=cfg, pool=pool)

    # Gerenciador de Prompts Versionados (PromptOps Langfuse + YAML local)
    prompt_provider: PromptProviderPort = PromptManager(cfg.prompts, settings=cfg)

    # Provedor Outbound (`console` | `meta`)
    if cfg.outbound.provider == "meta":
        outbound_provider: OutboundProviderProtocol = MetaOutboundProvider(
            access_token=cfg.whatsapp_access_token,
            phone_number_id=cfg.whatsapp_phone_number_id,
            api_version=cfg.outbound.meta_api_version,
            timeout_seconds=cfg.outbound.timeout_seconds,
        )
    else:
        outbound_provider = ConsoleOutboundProvider()

    outbound_sender = OutboundSender(outbound_provider, provider_name=cfg.outbound.provider)

    # Motor de Cognição (`echo` | `langgraph`)
    if cfg.cognition.agent_mode == "langgraph":
        model_adapter = ModelFactory.create(cfg.cognition.llm, settings=cfg)
        mw_pipeline = MiddlewarePipeline(
            [
                AuditRunMiddleware(agent_run_repo),
                LatencyTrackingMiddleware(),
                TokenBudgetMiddleware(
                    token_budget_store,
                    daily_limit=cfg.cognition.daily_token_budget_per_thread,
                ),
                ConversationMemoryMiddleware(
                    threads_repo,
                    max_messages_before_summary=cfg.cognition.context_max_messages_before_summary,
                ),
            ]
        )
        cognition_engine: CognitionEngineProtocol = LangGraphCognitionEngine(
            model_adapter=model_adapter,
            middleware_pipeline=mw_pipeline,
            guardrails_config=cfg.guardrails,
            retriever=retriever if cfg.rag.enabled else None,
            prompt_provider=prompt_provider,
            agent_name=cfg.prompts.default_prompt_name,
            rag_top_k=cfg.rag.top_k,
            settings=cfg,
        )
    else:
        cognition_engine = EchoCognitionEngine()

    worker_pipeline = ProcessQueueItemPipeline(
        queue_consumer=queue_consumer,
        cognition_engine=cognition_engine,
        outbound_sender=outbound_sender,
        threads_repo=threads_repo,
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
        rate_limiter=rate_limiter,
        media_router=media_router,
        threads_repo=threads_repo,
        retriever=retriever,
        prompt_provider=prompt_provider,
        token_budget_store=token_budget_store,
        agent_run_repo=agent_run_repo,
        cognition_engine=cognition_engine,
        outbound_provider=outbound_provider,
        outbound_sender=outbound_sender,
        worker_pipeline=worker_pipeline,
        worker_runner=worker_runner,
    )
