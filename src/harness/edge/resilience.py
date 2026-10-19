"""Resiliência de Borda: Fast-Retry (`tenacity`) + Quarentena (`Edge DLQ` — FR-003, FR-004).

Equivalente no C#/.NET: Políticas `Polly` (`WaitAndRetryAsync`) combinadas com um Dead-Letter Channel
para não perder nenhum webhook bruto nem travar a Meta com HTTP 500 em payloads corrompidos.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from harness.domain.queue import QuarantineEntry


class QuarantineRepositoryProtocol(Protocol):
    """Porta para persistência de payloads corrompidos na tabela `quarantine_inbound`."""

    async def save_quarantine_entry(self, entry: QuarantineEntry) -> None:
        """Persiste o registro de quarentena para auditoria operacional."""
        ...


class InMemoryQuarantineRepository:
    """Implementação em memória para testes unitários e simulação local sem banco."""

    def __init__(self) -> None:
        self.entries: list[QuarantineEntry] = []

    async def save_quarantine_entry(self, entry: QuarantineEntry) -> None:
        self.entries.append(entry)


async def execute_with_fast_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    initial_wait_ms: int = 50,
) -> T:
    """Executa uma operação assíncrona de banco na borda com Fast-Retry exponencial curto.

    Padrão: 3 tentativas com espera de 50ms -> 100ms -> 200ms (absorve micro-oscilações de rede).
    """
    initial_sec = max(initial_wait_ms / 1000.0, 0.01)

    @retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=initial_sec, min=initial_sec, max=0.5),
        retry=retry_if_exception_type((OSError, TimeoutError, ConnectionError)),
        reraise=True,
    )
    async def _wrapped() -> T:
        return await operation()

    return await _wrapped()


async def send_to_edge_quarantine(
    quarantine_repo: QuarantineRepositoryProtocol,
    *,
    raw_payload: dict[str, Any],
    headers: dict[str, str],
    error_reason: str,
    provider_message_id: str | None = None,
) -> QuarantineEntry:
    """Registra um payload inválido na Quarentena de Borda (Edge DLQ) sem derrubar o webhook."""
    entry = QuarantineEntry(
        provider_message_id=provider_message_id,
        raw_payload=raw_payload,
        headers=headers,
        error_reason=error_reason,
    )
    await quarantine_repo.save_quarantine_entry(entry)
    return entry

