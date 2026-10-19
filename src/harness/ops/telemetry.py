"""Observabilidade, Logging Estruturado (`structlog`), OpenTelemetry e Langfuse Tracing (`ops/telemetry.py` — FR-020, T045).

Equivalente no C#/.NET: `Serilog` (com `LogContext.PushProperty("CorrelationId", ...)`),
`OpenTelemetry.Extensions.Hosting` (`ActivitySource` / `Meter`) e `Langfuse` Tracing Handler.
"""

from contextvars import ContextVar
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from harness.settings import HarnessSettings

_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="system")
_thread_id_ctx: ContextVar[str] = ContextVar("thread_id", default="none")


def bind_execution_context(*, correlation_id: str = "system", thread_id: str = "none") -> None:
    """Associa `correlation_id` e `thread_id` ao contexto assíncrono atual (equivalente a `AsyncLocal<T>` no .NET)."""
    _correlation_id_ctx.set(correlation_id)
    _thread_id_ctx.set(thread_id)
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        thread_id=thread_id,
    )


def configure_observability(settings: HarnessSettings) -> None:
    """Configura `structlog` (JSON ou Console) e inicializa o `TracerProvider` do OpenTelemetry."""
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if settings.observability.json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(20),
        cache_logger_on_first_use=True,
    )

    if settings.observability.otel_enabled:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)


def get_logger(component: str = "harness") -> Any:
    """Retorna um logger estruturado enriquecido com o nome do componente."""
    return structlog.get_logger(component=component)


def get_langfuse_callback_handler(
    settings: HarnessSettings,
    *,
    session_id: str | None = None,
    trace_name: str = "whatsapp_agent_turn",
) -> Any | None:
    """Cria um `CallbackHandler` do Langfuse se habilitado e com chaves presentes; caso contrário retorna `None`."""
    if not settings.observability.langfuse_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            session_id=session_id,
            trace_name=trace_name,
        )
    except Exception:
        return None

