"""Adaptadores de Fila Transacional: `PostgresQueueAdapter` e `InMemoryQueueAdapter` (T021).

Cumprem simultaneamente `QueueEnqueuerProtocol` e `QueueConsumerProtocol` (SOLID ISP & DIP):
1. Idempotência estrita por `provider_message_id` (`inbound_dedup` — FR-005).
2. Debounce Persistido (`scheduled_for = now() + debounce_seconds`): concatena mensagens rápidas da
   mesma `thread_id` que ainda estão em estado `pending` (FR-006).
3. Claim Atômico concorrente via `SELECT ... FOR UPDATE SKIP LOCKED` (FR-008).
4. Transição transacional `pending -> processing -> done | dead` com backoff exponencial (FR-009).
"""

import asyncio
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from uuid import UUID, uuid4

from psycopg_pool import AsyncConnectionPool

from harness.domain.events import QueueStats
from harness.domain.message import NormalizedTextMessage
from harness.domain.queue import QuarantineEntry, QueueItem
from harness.domain.value_objects import QueueStatus, ThreadMode


class PostgresQueueAdapter:
    """Implementação em PostgreSQL 16 usando `SKIP LOCKED` e índice parcial de debounce."""

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        max_retries: int = 3,
    ) -> None:
        self._pool = pool
        self._max_retries = max_retries

    async def enqueue_with_debounce(
        self,
        message: NormalizedTextMessage,
        debounce_seconds: float,
    ) -> UUID | None:
        """Garante idempotência e insere/concatena mensagem pendente para a `thread_id`."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Garante existência da Thread
                await cur.execute(
                    """
                    INSERT INTO threads (thread_id, phone_number)
                    VALUES (%s, %s)
                    ON CONFLICT (thread_id) DO UPDATE SET updated_at = NOW()
                    RETURNING mode;
                    """,
                    (message.thread_id, message.sender_phone),
                )
                thread_row = await cur.fetchone()
                thread_mode = str(thread_row["mode"]) if thread_row else ThreadMode.BOT.value

                # 2. Idempotência: descarta silenciosamente se provider_message_id já existir
                await cur.execute(
                    """
                    INSERT INTO inbound_dedup (provider_message_id, thread_id)
                    VALUES (%s, %s)
                    ON CONFLICT (provider_message_id) DO NOTHING
                    RETURNING provider_message_id;
                    """,
                    (message.provider_message_id, message.thread_id),
                )
                dedup_row = await cur.fetchone()
                if dedup_row is None:
                    await conn.commit()
                    return None

                # 3. Registra no histórico operacional da thread
                await cur.execute(
                    """
                    INSERT INTO thread_messages (thread_id, role, content)
                    VALUES (%s, 'user', %s);
                    """,
                    (message.thread_id, message.text_content),
                )

                # Se a thread estiver em modo HUMAN ou PAUSED (Handoff — FR-015), não enfileira para a LLM
                if thread_mode != ThreadMode.BOT.value:
                    await conn.commit()
                    return None

                # 4. Upsert de Debounce no Postgres usando o índice parcial idx_queue_unique_pending_thread
                msg_ids_json = json.dumps([message.provider_message_id])
                await cur.execute(
                    """
                    INSERT INTO queue_items (
                        thread_id,
                        concatenated_text,
                        provider_message_ids,
                        status,
                        max_retries,
                        scheduled_for
                    )
                    VALUES (
                        %s,
                        %s,
                        %s::jsonb,
                        'pending',
                        %s,
                        NOW() + (%s * INTERVAL '1 second')
                    )
                    ON CONFLICT (thread_id) WHERE status = 'pending'
                    DO UPDATE SET
                        concatenated_text = queue_items.concatenated_text || E'\\n' || EXCLUDED.concatenated_text,
                        provider_message_ids = queue_items.provider_message_ids || EXCLUDED.provider_message_ids,
                        scheduled_for = NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    RETURNING id;
                    """,
                    (
                        message.thread_id,
                        message.text_content,
                        msg_ids_json,
                        self._max_retries,
                        debounce_seconds,
                        debounce_seconds,
                    ),
                )
                row = await cur.fetchone()
            await conn.commit()
            return UUID(str(row["id"])) if row else None

    async def claim_next_ready(self, worker_id: str) -> QueueItem | None:
        """Faz claim atômico concorrente (`FOR UPDATE SKIP LOCKED`) do próximo item elegível."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    WITH next_item AS (
                        SELECT id
                        FROM queue_items
                        WHERE status = 'pending'
                          AND scheduled_for <= NOW()
                        ORDER BY scheduled_for ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE queue_items q
                    SET status = 'processing',
                        locked_by = %s,
                        claimed_at = NOW(),
                        updated_at = NOW()
                    FROM next_item
                    WHERE q.id = next_item.id
                    RETURNING q.*;
                    """,
                    (worker_id,),
                )
                row = await cur.fetchone()
            await conn.commit()
            return self._row_to_item(row) if row else None

    async def mark_done(self, item_id: UUID) -> None:
        """Marca o item como `done` após confirmação de entrega do Outbound."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE queue_items
                    SET status = 'done',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (item_id,),
                )
            await conn.commit()

    async def mark_failed_or_dead(
        self,
        item_id: UUID,
        error_message: str,
        backoff_seconds: float,
    ) -> QueueItem:
        """Incrementa `attempts`; se atingir `max_retries` marca `dead`, senão reagenda `pending`."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE queue_items
                    SET attempts = attempts + 1,
                        last_error = %s,
                        status = CASE
                            WHEN attempts + 1 >= max_retries THEN 'dead'
                            ELSE 'pending'
                        END,
                        scheduled_for = CASE
                            WHEN attempts + 1 >= max_retries THEN scheduled_for
                            ELSE NOW() + ((%s * POWER(2, attempts)) * INTERVAL '1 second')
                        END,
                        locked_by = NULL,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *;
                    """,
                    (error_message, backoff_seconds, item_id),
                )
                row = await cur.fetchone()
            await conn.commit()
            if not row:
                raise KeyError(f"QueueItem {item_id} não encontrado no banco.")
            return self._row_to_item(row)

    async def reprocess_dead_items(self) -> int:
        """Move todos os itens `dead` de volta para `pending` com `attempts = 0` (FR-018)."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    WITH target_dead AS (
                        SELECT id
                        FROM queue_items q
                        WHERE q.status = 'dead'
                          AND NOT EXISTS (
                              SELECT 1 FROM queue_items p
                              WHERE p.thread_id = q.thread_id AND p.status = 'pending'
                          )
                    )
                    UPDATE queue_items q
                    SET status = 'pending',
                        attempts = 0,
                        last_error = NULL,
                        scheduled_for = NOW(),
                        updated_at = NOW()
                    FROM target_dead
                    WHERE q.id = target_dead.id;
                    """
                )
                count = cur.rowcount or 0
            await conn.commit()
            return count

    async def get_stats(self) -> QueueStats:
        """Consulta contagem atual de itens por estado e quarentena."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'processing') AS processing,
                    COUNT(*) FILTER (WHERE status = 'done') AS done,
                    COUNT(*) FILTER (WHERE status = 'dead') AS dead,
                    (SELECT COUNT(*) FROM quarantine_inbound) AS quarantined_inbound
                FROM queue_items;
                """
            )
            row = await cur.fetchone() or {}
            return QueueStats(
                pending=int(row.get("pending", 0)),
                processing=int(row.get("processing", 0)),
                done=int(row.get("done", 0)),
                dead=int(row.get("dead", 0)),
                quarantined_inbound=int(row.get("quarantined_inbound", 0)),
            )

    async def save_quarantine_entry(self, entry: QuarantineEntry) -> None:
        """Persiste um registro de quarentena de borda na tabela `quarantine_inbound`."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO quarantine_inbound (id, provider_message_id, raw_payload, headers, error_reason)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb, %s);
                    """,
                    (
                        entry.id,
                        entry.provider_message_id,
                        json.dumps(entry.raw_payload),
                        json.dumps(entry.headers),
                        entry.error_reason,
                    ),
                )
            await conn.commit()

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> QueueItem:
        raw_ids = row.get("provider_message_ids", [])
        if isinstance(raw_ids, str):
            raw_ids = json.loads(raw_ids)
        return QueueItem(
            id=UUID(str(row["id"])),
            thread_id=str(row["thread_id"]),
            concatenated_text=str(row["concatenated_text"]),
            provider_message_ids=list(raw_ids),
            status=QueueStatus(str(row["status"])),
            attempts=int(row["attempts"]),
            max_retries=int(row["max_retries"]),
            last_error=row.get("last_error"),
            locked_by=row.get("locked_by"),
            scheduled_for=row["scheduled_for"],
            claimed_at=row.get("claimed_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class InMemoryQueueAdapter:
    """Implementação fiel da `QueuePort` em memória com `asyncio.Lock` para testes rápidos e modo offline."""

    def __init__(self, *, max_retries: int = 3) -> None:
        self._lock = asyncio.Lock()
        self._max_retries = max_retries
        self._seen_message_ids: set[str] = set()
        self._items: dict[UUID, QueueItem] = {}
        self._thread_modes: dict[str, ThreadMode] = {}
        self._quarantine: list[QuarantineEntry] = []

    def set_thread_mode(self, thread_id: str, mode: ThreadMode) -> None:
        """Permite alternar o modo da thread (`bot | human | paused`) para testes de Handoff."""
        self._thread_modes[thread_id] = mode

    async def enqueue_with_debounce(
        self,
        message: NormalizedTextMessage,
        debounce_seconds: float,
    ) -> UUID | None:
        async with self._lock:
            if message.provider_message_id in self._seen_message_ids:
                return None
            self._seen_message_ids.add(message.provider_message_id)

            mode = self._thread_modes.get(message.thread_id, ThreadMode.BOT)
            if mode != ThreadMode.BOT:
                return None

            now = datetime.now(UTC)
            scheduled = now + timedelta(seconds=debounce_seconds)

            # Procura item pending existente para a mesma thread_id (Debounce)
            for existing in self._items.values():
                if existing.thread_id == message.thread_id and existing.status == QueueStatus.PENDING:
                    existing.concatenated_text = f"{existing.concatenated_text}\n{message.text_content}"
                    existing.provider_message_ids.append(message.provider_message_id)
                    existing.scheduled_for = scheduled
                    existing.updated_at = now
                    return existing.id

            new_item = QueueItem(
                id=uuid4(),
                thread_id=message.thread_id,
                concatenated_text=message.text_content,
                provider_message_ids=[message.provider_message_id],
                status=QueueStatus.PENDING,
                max_retries=self._max_retries,
                scheduled_for=scheduled,
                created_at=now,
                updated_at=now,
            )
            self._items[new_item.id] = new_item
            return new_item.id

    async def claim_next_ready(self, worker_id: str) -> QueueItem | None:
        async with self._lock:
            now = datetime.now(UTC)
            ready = [
                item
                for item in self._items.values()
                if item.status == QueueStatus.PENDING and item.scheduled_for <= now
            ]
            if not ready:
                return None
            ready.sort(key=lambda x: x.scheduled_for)
            target = ready[0]
            target.status = QueueStatus.PROCESSING
            target.locked_by = worker_id
            target.claimed_at = now
            target.updated_at = now
            return target.model_copy(deep=True)

    async def mark_done(self, item_id: UUID) -> None:
        async with self._lock:
            item = self._items[item_id]
            item.status = QueueStatus.DONE
            item.completed_at = datetime.now(UTC)
            item.updated_at = datetime.now(UTC)

    async def mark_failed_or_dead(
        self,
        item_id: UUID,
        error_message: str,
        backoff_seconds: float,
    ) -> QueueItem:
        async with self._lock:
            item = self._items[item_id]
            now = datetime.now(UTC)
            item.attempts += 1
            item.last_error = error_message
            item.locked_by = None
            item.updated_at = now
            if item.attempts >= item.max_retries:
                item.status = QueueStatus.DEAD
            else:
                delay = backoff_seconds * (2 ** (item.attempts - 1))
                item.status = QueueStatus.PENDING
                item.scheduled_for = now + timedelta(seconds=delay)
            return item.model_copy(deep=True)

    async def reprocess_dead_items(self) -> int:
        async with self._lock:
            count = 0
            now = datetime.now(UTC)
            for item in self._items.values():
                if item.status == QueueStatus.DEAD:
                    has_pending = any(
                        other.thread_id == item.thread_id and other.status == QueueStatus.PENDING
                        for other in self._items.values()
                    )
                    if not has_pending:
                        item.status = QueueStatus.PENDING
                        item.attempts = 0
                        item.last_error = None
                        item.scheduled_for = now
                        item.updated_at = now
                        count += 1
            return count

    async def get_stats(self) -> QueueStats:
        async with self._lock:
            return QueueStats(
                pending=sum(1 for i in self._items.values() if i.status == QueueStatus.PENDING),
                processing=sum(1 for i in self._items.values() if i.status == QueueStatus.PROCESSING),
                done=sum(1 for i in self._items.values() if i.status == QueueStatus.DONE),
                dead=sum(1 for i in self._items.values() if i.status == QueueStatus.DEAD),
                quarantined_inbound=len(self._quarantine),
            )

    async def save_quarantine_entry(self, entry: QuarantineEntry) -> None:
        async with self._lock:
            self._quarantine.append(entry)

