"""Proteção Anti-Loop Bot-to-Bot e Rate Limit por Janela de Tempo (`edge/rate_limit.py` — T030).

Equivalente no C#/.NET: `RateLimiter` (`System.Threading.RateLimiting.FixedWindowRateLimiter`)
acoplado ao estado da `Thread` no banco de dados ou em memória.
Impede que outro bot em loop infinito ou um usuário mal-intencionado esgote a cota de LLM (FR-001).
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from harness.domain.exceptions import RateLimitExceededError
from harness.domain.value_objects import PhoneNumber, ThreadId


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Porta de verificação de taxa de mensagens por número de telefone."""

    async def check_and_increment(self, phone_number: str) -> None:
        """Verifica se o remetente está dentro do limite da janela atual; lança `RateLimitExceededError` se exceder."""
        ...


class InMemoryRateLimiter:
    """Implementação em memória de janela fixa por telefone (para testes e modo `in_memory`)."""

    def __init__(self, *, window_seconds: int = 60, max_messages: int = 20) -> None:
        self._window_seconds = window_seconds
        self._max_messages = max_messages
        self._windows: dict[str, tuple[datetime, int]] = {}

    async def check_and_increment(self, phone_number: str) -> None:
        now = datetime.now(UTC)
        phone_key = str(PhoneNumber(phone_number))
        window_start, count = self._windows.get(phone_key, (now, 0))

        if (now - window_start).total_seconds() >= self._window_seconds:
            self._windows[phone_key] = (now, 1)
            return

        new_count = count + 1
        self._windows[phone_key] = (window_start, new_count)
        if new_count > self._max_messages:
            raise RateLimitExceededError(
                phone_number=phone_key,
                message=(
                    f"Limite de {self._max_messages} mensagens a cada "
                    f"{self._window_seconds}s excedido para {phone_key}."
                ),
            )


class PostgresRateLimiter:
    """Implementação transacional apoiada nas colunas `rate_window_start` e `rate_window_count` da tabela `threads`."""

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        window_seconds: int = 60,
        max_messages: int = 20,
    ) -> None:
        self._pool = pool
        self._window_seconds = window_seconds
        self._max_messages = max_messages

    async def check_and_increment(self, phone_number: str) -> None:
        now = datetime.now(UTC)
        phone_vo = PhoneNumber(phone_number)
        thread_vo = ThreadId.from_phone(phone_vo)
        window_cutoff = now - timedelta(seconds=self._window_seconds)

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO threads (
                            thread_id, phone_number, mode, rate_window_start, rate_window_count, updated_at
                        )
                        VALUES (%s, %s, 'bot', %s, 1, %s)
                        ON CONFLICT (thread_id) DO UPDATE
                        SET
                            rate_window_count = CASE
                                WHEN threads.rate_window_start <= %s THEN 1
                                ELSE threads.rate_window_count + 1
                            END,
                            rate_window_start = CASE
                                WHEN threads.rate_window_start <= %s THEN EXCLUDED.rate_window_start
                                ELSE threads.rate_window_start
                            END,
                            updated_at = EXCLUDED.updated_at
                        RETURNING rate_window_count;
                        """,
                        (
                            str(thread_vo),
                            str(phone_vo),
                            now,
                            now,
                            window_cutoff,
                            window_cutoff,
                        ),
                    )
                    row = await cur.fetchone()
                    if row and int(row["rate_window_count"]) > self._max_messages:
                        raise RateLimitExceededError(
                            phone_number=str(phone_vo),
                            message=(
                                f"Limite de {self._max_messages} mensagens a cada "
                                f"{self._window_seconds}s excedido para {phone_vo}."
                            ),
                        )

