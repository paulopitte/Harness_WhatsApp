"""Repositório de Persistência de Threads, Histórico Operacional e Memória Semântica (`persistence/threads_repo.py` — FR-014, FR-015, T037).

Equivalente no C#/.NET: `IThreadsRepository` implementado com Entity Framework Core / Dapper (`PostgresThreadsRepository`)
e `InMemoryThreadsRepository` para testes rápidos sem banco externo.

Materializa os Pilares 2 e 3 da Harness ("Contexto como política" e "Memória como sistema"):
- `thread_messages WHERE is_summarized = FALSE`: Janela deslizante ativa da conversa atual.
- `threads.conversation_summary`: Memória operacional compactada quando a janela atinge o limite.
- `semantic_facts`: Memória durável de longo prazo sobre o cliente (ex.: nome, empresa, preferências).
"""

from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from harness.domain.thread import SemanticFact, Thread, ThreadMessage
from harness.domain.value_objects import ThreadId, ThreadMode


@runtime_checkable
class ThreadsRepositoryProtocol(Protocol):
    """Porta de persistência para o agregado `Thread`, janela `ThreadMessage` e `SemanticFact`."""

    async def get_or_create_thread(self, thread_id: str) -> Thread: ...

    async def set_thread_mode(self, thread_id: str, mode: ThreadMode) -> Thread: ...

    async def append_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> ThreadMessage: ...

    async def get_active_messages(self, thread_id: str) -> list[ThreadMessage]: ...

    async def compact_messages_with_summary(
        self,
        thread_id: str,
        new_summary: str,
        *,
        keep_recent: int = 2,
    ) -> None: ...

    async def upsert_semantic_fact(
        self,
        thread_id: str,
        fact_key: str,
        fact_value: str,
        confidence: float = 1.0,
    ) -> SemanticFact: ...

    async def get_semantic_facts(self, thread_id: str) -> dict[str, str]: ...

    async def list_threads(self, limit: int = 50) -> list[Thread]: ...

    async def get_all_messages(
        self, thread_id: str, limit: int = 100
    ) -> list[ThreadMessage]: ...


class InMemoryThreadsRepository:
    """Implementação em memória com paridade comportamental em relação ao PostgreSQL."""

    def __init__(self) -> None:
        self._threads: dict[str, Thread] = {}
        self._messages: dict[str, list[ThreadMessage]] = {}
        self._facts: dict[str, dict[str, SemanticFact]] = {}

    async def get_or_create_thread(self, thread_id: str) -> Thread:
        vo = ThreadId(thread_id)
        key = str(vo)
        if key not in self._threads:
            self._threads[key] = Thread(
                thread_id=key,
                phone_number=vo.phone_number,
                mode=ThreadMode.BOT,
                conversation_summary="",
            )
        return self._threads[key]

    async def set_thread_mode(self, thread_id: str, mode: ThreadMode) -> Thread:
        thread = await self.get_or_create_thread(thread_id)
        updated = thread.model_copy(
            update={"mode": mode, "updated_at": datetime.now(UTC)}
        )
        self._threads[thread.thread_id] = updated
        return updated

    async def append_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> ThreadMessage:
        thread = await self.get_or_create_thread(thread_id)
        msg = ThreadMessage(
            id=uuid4(),
            thread_id=thread.thread_id,
            role=role,
            content=content,
            is_summarized=False,
            created_at=datetime.now(UTC),
        )
        self._messages.setdefault(thread.thread_id, []).append(msg)
        return msg

    async def get_active_messages(self, thread_id: str) -> list[ThreadMessage]:
        key = str(ThreadId(thread_id))
        msgs = self._messages.get(key, [])
        return [m for m in msgs if not m.is_summarized]

    async def compact_messages_with_summary(
        self,
        thread_id: str,
        new_summary: str,
        *,
        keep_recent: int = 2,
    ) -> None:
        thread = await self.get_or_create_thread(thread_id)
        key = thread.thread_id
        self._threads[key] = thread.model_copy(
            update={
                "conversation_summary": new_summary.strip(),
                "updated_at": datetime.now(UTC),
            }
        )

        all_msgs = self._messages.get(key, [])
        active_indices = [idx for idx, m in enumerate(all_msgs) if not m.is_summarized]
        to_summarize = (
            active_indices[:-keep_recent] if keep_recent > 0 else active_indices
        )
        for idx in to_summarize:
            all_msgs[idx] = all_msgs[idx].model_copy(update={"is_summarized": True})

    async def upsert_semantic_fact(
        self,
        thread_id: str,
        fact_key: str,
        fact_value: str,
        confidence: float = 1.0,
    ) -> SemanticFact:
        thread = await self.get_or_create_thread(thread_id)
        key = thread.thread_id
        normalized_fact_key = fact_key.strip().lower()
        fact = SemanticFact(
            id=uuid4(),
            thread_id=key,
            fact_key=normalized_fact_key,
            fact_value=fact_value.strip(),
            confidence=confidence,
            updated_at=datetime.now(UTC),
        )
        self._facts.setdefault(key, {})[normalized_fact_key] = fact
        return fact

    async def get_semantic_facts(self, thread_id: str) -> dict[str, str]:
        key = str(ThreadId(thread_id))
        thread_facts = self._facts.get(key, {})
        return {k: v.fact_value for k, v in thread_facts.items()}

    async def list_threads(self, limit: int = 50) -> list[Thread]:
        threads = list(self._threads.values())
        threads.sort(key=lambda t: t.updated_at, reverse=True)
        return threads[:limit]

    async def get_all_messages(
        self, thread_id: str, limit: int = 100
    ) -> list[ThreadMessage]:
        key = str(ThreadId(thread_id))
        msgs = self._messages.get(key, [])
        return msgs[-limit:]


class PostgresThreadsRepository:
    """Implementação PostgreSQL transacional para `threads`, `thread_messages` e `semantic_facts`."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def get_or_create_thread(self, thread_id: str) -> Thread:
        vo = ThreadId(thread_id)
        key = str(vo)
        now = datetime.now(UTC)

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO threads (thread_id, phone_number, mode, created_at, updated_at)
                        VALUES (%s, %s, 'bot', %s, %s)
                        ON CONFLICT (thread_id) DO UPDATE
                        SET updated_at = threads.updated_at
                        RETURNING *;
                        """,
                        (key, vo.phone_number, now, now),
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    return self._map_thread(row)

    async def set_thread_mode(self, thread_id: str, mode: ThreadMode) -> Thread:
        await self.get_or_create_thread(thread_id)
        key = str(ThreadId(thread_id))
        now = datetime.now(UTC)

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE threads
                        SET mode = %s, updated_at = %s
                        WHERE thread_id = %s
                        RETURNING *;
                        """,
                        (str(mode), now, key),
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    return self._map_thread(row)

    async def append_message(
        self,
        thread_id: str,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> ThreadMessage:
        thread = await self.get_or_create_thread(thread_id)
        msg_id = uuid4()
        now = datetime.now(UTC)

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO thread_messages (id, thread_id, role, content, is_summarized, created_at)
                        VALUES (%s, %s, %s, %s, FALSE, %s)
                        RETURNING *;
                        """,
                        (msg_id, thread.thread_id, role, content, now),
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    return ThreadMessage(
                        id=row["id"],
                        thread_id=row["thread_id"],
                        role=row["role"],
                        content=row["content"],
                        is_summarized=bool(row["is_summarized"]),
                        created_at=row["created_at"],
                    )

    async def get_active_messages(self, thread_id: str) -> list[ThreadMessage]:
        key = str(ThreadId(thread_id))
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT id, thread_id, role, content, is_summarized, created_at
                    FROM thread_messages
                    WHERE thread_id = %s AND is_summarized = FALSE
                    ORDER BY created_at ASC;
                    """,
                    (key,),
                )
                rows = await cur.fetchall()
                return [
                    ThreadMessage(
                        id=r["id"],
                        thread_id=r["thread_id"],
                        role=r["role"],
                        content=r["content"],
                        is_summarized=bool(r["is_summarized"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

    async def compact_messages_with_summary(
        self,
        thread_id: str,
        new_summary: str,
        *,
        keep_recent: int = 2,
    ) -> None:
        key = str(ThreadId(thread_id))
        now = datetime.now(UTC)

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE threads
                        SET conversation_summary = %s, updated_at = %s
                        WHERE thread_id = %s;
                        """,
                        (new_summary.strip(), now, key),
                    )
                    await cur.execute(
                        """
                        WITH active AS (
                            SELECT id
                            FROM thread_messages
                            WHERE thread_id = %s AND is_summarized = FALSE
                            ORDER BY created_at DESC
                            OFFSET %s
                        )
                        UPDATE thread_messages
                        SET is_summarized = TRUE
                        WHERE id IN (SELECT id FROM active);
                        """,
                        (key, max(0, keep_recent)),
                    )

    async def upsert_semantic_fact(
        self,
        thread_id: str,
        fact_key: str,
        fact_value: str,
        confidence: float = 1.0,
    ) -> SemanticFact:
        thread = await self.get_or_create_thread(thread_id)
        normalized_key = fact_key.strip().lower()
        now = datetime.now(UTC)
        fact_id = uuid4()

        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO semantic_facts (id, thread_id, fact_key, fact_value, confidence, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (thread_id, fact_key) DO UPDATE
                        SET
                            fact_value = EXCLUDED.fact_value,
                            confidence = EXCLUDED.confidence,
                            updated_at = EXCLUDED.updated_at
                        RETURNING *;
                        """,
                        (
                            fact_id,
                            thread.thread_id,
                            normalized_key,
                            fact_value.strip(),
                            confidence,
                            now,
                        ),
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    return SemanticFact(
                        id=row["id"],
                        thread_id=row["thread_id"],
                        fact_key=row["fact_key"],
                        fact_value=row["fact_value"],
                        confidence=float(row["confidence"]),
                        updated_at=row["updated_at"],
                    )

    async def get_semantic_facts(self, thread_id: str) -> dict[str, str]:
        key = str(ThreadId(thread_id))
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT fact_key, fact_value
                    FROM semantic_facts
                    WHERE thread_id = %s
                    ORDER BY updated_at ASC;
                    """,
                    (key,),
                )
                rows = await cur.fetchall()
                return {str(r["fact_key"]): str(r["fact_value"]) for r in rows}

    async def list_threads(self, limit: int = 50) -> list[Thread]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT thread_id, phone_number, mode, conversation_summary,
                           daily_tokens_used, daily_tokens_reset_at,
                           rate_window_start, rate_window_count,
                           created_at, updated_at
                    FROM threads
                    ORDER BY updated_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()
                return [self._map_thread(r) for r in rows]

    async def get_all_messages(
        self, thread_id: str, limit: int = 100
    ) -> list[ThreadMessage]:
        key = str(ThreadId(thread_id))
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT id, thread_id, role, content, is_summarized, created_at
                    FROM thread_messages
                    WHERE thread_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s;
                    """,
                    (key, limit),
                )
                rows = await cur.fetchall()
                return [
                    ThreadMessage(
                        id=r["id"],
                        thread_id=r["thread_id"],
                        role=r["role"],
                        content=r["content"],
                        is_summarized=bool(r["is_summarized"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

    @staticmethod
    def _map_thread(row: dict[str, Any]) -> Thread:
        return Thread(
            thread_id=row["thread_id"],
            phone_number=row["phone_number"],
            mode=ThreadMode(row["mode"]),
            conversation_summary=row["conversation_summary"] or "",
            daily_tokens_used=int(row["daily_tokens_used"]),
            daily_tokens_reset_at=row["daily_tokens_reset_at"],
            rate_window_start=row["rate_window_start"],
            rate_window_count=int(row["rate_window_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

