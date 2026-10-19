"""Repositório de Auditoria de Execuções (`agent_runs`) e Consulta de Quarentena (`quarantine_inbound`) (`persistence/runs_repo.py` — T046).

Equivalente no C#/.NET: Read/Write Repository para inspeção operacional pela Admin API (`ops/admin_api.py`),
permitindo listar os turnos executados pelo agente (`AgentRunRecord`) e os eventos barrados na borda (`QuarantineEntry`).
"""

from typing import Any, Protocol, runtime_checkable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from harness.cognition.middlewares import (
    AgentRunRepositoryProtocol,
    InMemoryAgentRunRepository,
    PostgresAgentRunRepository,
)
from harness.domain.events import AgentRunRecord
from harness.domain.queue import QuarantineEntry
from harness.domain.value_objects import RunStatus
from harness.edge.resilience import InMemoryQuarantineRepository


@runtime_checkable
class RunsQueryRepositoryProtocol(AgentRunRepositoryProtocol, Protocol):
    """Porta completa para escrita e listagem de execuções do agente e quarentena."""

    async def list_recent_runs(self, limit: int = 50) -> list[AgentRunRecord]: ...

    async def list_quarantine_entries(self, limit: int = 50) -> list[QuarantineEntry]: ...


class InMemoryRunsRepository(InMemoryAgentRunRepository):
    """Implementação em memória para gravação e listagem de `AgentRunRecord` e `QuarantineEntry`."""

    def __init__(self, quarantine_repo: InMemoryQuarantineRepository | None = None) -> None:
        super().__init__()
        self._quarantine_repo = quarantine_repo

    async def list_recent_runs(self, limit: int = 50) -> list[AgentRunRecord]:
        return list(reversed(self.runs[-limit:]))

    async def list_quarantine_entries(self, limit: int = 50) -> list[QuarantineEntry]:
        if self._quarantine_repo is None:
            return []
        return list(reversed(self._quarantine_repo.entries[-limit:]))


class PostgresRunsRepository(PostgresAgentRunRepository):
    """Implementação PostgreSQL para gravação e consulta de `agent_runs` e `quarantine_inbound`."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        super().__init__(pool)

    async def list_recent_runs(self, limit: int = 50) -> list[AgentRunRecord]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT *
                    FROM agent_runs
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()
                return [
                    AgentRunRecord(
                        id=r["id"],
                        queue_item_id=r["queue_item_id"],
                        thread_id=r["thread_id"],
                        agent_name=r["agent_name"],
                        llm_provider=r["llm_provider"],
                        llm_model=r["llm_model"],
                        prompt_version=r["prompt_version"],
                        prompt_tokens=int(r["prompt_tokens"]),
                        completion_tokens=int(r["completion_tokens"]),
                        latency_ms=int(r["latency_ms"]),
                        guardrail_triggered=bool(r["guardrail_triggered"]),
                        guardrail_reason=r["guardrail_reason"],
                        status=RunStatus(r["status"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

    async def list_quarantine_entries(self, limit: int = 50) -> list[QuarantineEntry]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT *
                    FROM quarantine_inbound
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()
                return [
                    QuarantineEntry(
                        id=r["id"],
                        provider_message_id=r["provider_message_id"],
                        raw_payload=r["raw_payload"] or {},
                        headers=r["headers"] or {},
                        error_reason=r["error_reason"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]

