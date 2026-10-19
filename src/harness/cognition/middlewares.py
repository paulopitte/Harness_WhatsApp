"""Pipeline Extensível de Middlewares do Agente (`cognition/middlewares.py` — FR-014, FR-017, T033, T038).

Equivalente no C#/.NET: `IPipelineBehavior<TRequest, TResponse>` do **MediatR** ou
`DelegatingHandler` do `HttpClient`.
Permite interceptar cada execução do agente (antes e depois do grafo LangGraph) para:
1. `LatencyTrackingMiddleware`: Medir a duração exata em milissegundos (`time.perf_counter`).
2. `TokenBudgetMiddleware`: Controlar e impor o orçamento diário de tokens por `thread_id`.
3. `ConversationMemoryMiddleware`: Carregar/atualizar Dupla Memória (`thread_messages`, `conversation_summary` e `semantic_facts`) com auto-sumarização (FR-014).
4. `AuditRunMiddleware`: Persistir o `AgentRunRecord` completo na tabela `agent_runs` (ou em memória).
"""

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from harness.domain.events import AgentRunRecord
from harness.domain.exceptions import TokenBudgetExceededError
from harness.domain.value_objects import RunStatus, ThreadId
from harness.persistence.threads_repo import ThreadsRepositoryProtocol


@dataclass
class MiddlewareContext:
    """Contexto mutável compartilhado ao longo dos Middlewares de uma execução de turno."""

    thread_id: ThreadId
    user_text: str
    queue_item_id: UUID | None = None
    agent_name: str = "default_agent"
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    prompt_version: str = "local-1.0.0"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    guardrail_triggered: bool = False
    guardrail_reason: str | None = None
    status: RunStatus = RunStatus.SUCCESS
    conversation_summary: str = ""
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    semantic_facts: dict[str, str] = field(default_factory=dict)


NextMiddlewareCallable = Callable[[MiddlewareContext], Awaitable[str]]


@runtime_checkable
class CognitionMiddlewareProtocol(Protocol):
    """Interface de um Middleware no pipeline de cognição (equivalente a `IPipelineBehavior`)."""

    async def invoke(
        self,
        context: MiddlewareContext,
        call_next: NextMiddlewareCallable,
    ) -> str:
        """Executa lógica pré/pós invocação do próximo elo da cadeia."""
        ...


# ==============================================================================
# 1. Stores de Orçamento de Tokens (`TokenBudgetStoreProtocol`)
# ==============================================================================


@runtime_checkable
class TokenBudgetStoreProtocol(Protocol):
    """Porta de leitura e incremento do consumo diário de tokens de uma `thread_id`."""

    async def get_daily_tokens_used(self, thread_id: str) -> int: ...

    async def add_daily_tokens(self, thread_id: str, tokens: int) -> int: ...


class InMemoryTokenBudgetStore:
    """Armazenamento em memória do orçamento diário de tokens por `thread_id`."""

    def __init__(self) -> None:
        self._usage: dict[str, tuple[datetime, int]] = {}

    async def get_daily_tokens_used(self, thread_id: str) -> int:
        now = datetime.now(UTC)
        reset_at, used = self._usage.get(thread_id, (now, 0))
        if (now - reset_at) >= timedelta(days=1):
            self._usage[thread_id] = (now, 0)
            return 0
        return used

    async def add_daily_tokens(self, thread_id: str, tokens: int) -> int:
        current = await self.get_daily_tokens_used(thread_id)
        now = datetime.now(UTC)
        reset_at, _ = self._usage.get(thread_id, (now, 0))
        updated = current + max(0, tokens)
        self._usage[thread_id] = (reset_at, updated)
        return updated


class PostgresTokenBudgetStore:
    """Armazenamento em PostgreSQL do orçamento diário nas colunas `daily_tokens_used` da tabela `threads`."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def get_daily_tokens_used(self, thread_id: str) -> int:
        now = datetime.now(UTC)
        day_cutoff = now - timedelta(days=1)
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT daily_tokens_used, daily_tokens_reset_at
                    FROM threads
                    WHERE thread_id = %s;
                    """,
                    (thread_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return 0
                if row["daily_tokens_reset_at"] <= day_cutoff:
                    return 0
                return int(row["daily_tokens_used"])

    async def add_daily_tokens(self, thread_id: str, tokens: int) -> int:
        now = datetime.now(UTC)
        day_cutoff = now - timedelta(days=1)
        phone_guess = ThreadId(thread_id).phone_number
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO threads (
                            thread_id, phone_number, mode, daily_tokens_used, daily_tokens_reset_at, updated_at
                        )
                        VALUES (%s, %s, 'bot', %s, %s, %s)
                        ON CONFLICT (thread_id) DO UPDATE
                        SET
                            daily_tokens_used = CASE
                                WHEN threads.daily_tokens_reset_at <= %s THEN EXCLUDED.daily_tokens_used
                                ELSE threads.daily_tokens_used + EXCLUDED.daily_tokens_used
                            END,
                            daily_tokens_reset_at = CASE
                                WHEN threads.daily_tokens_reset_at <= %s THEN EXCLUDED.daily_tokens_reset_at
                                ELSE threads.daily_tokens_reset_at
                            END,
                            updated_at = EXCLUDED.updated_at
                        RETURNING daily_tokens_used;
                        """,
                        (
                            thread_id,
                            phone_guess,
                            max(0, tokens),
                            now,
                            now,
                            day_cutoff,
                            day_cutoff,
                        ),
                    )
                    row = await cur.fetchone()
                    return int(row["daily_tokens_used"]) if row else max(0, tokens)


# ==============================================================================
# 2. Repositório de Auditoria de Execuções (`AgentRunRepositoryProtocol`)
# ==============================================================================


@runtime_checkable
class AgentRunRepositoryProtocol(Protocol):
    """Porta para persistência e consulta de `AgentRunRecord` (auditoria de cognição)."""

    async def save_run(self, record: AgentRunRecord) -> None: ...


class InMemoryAgentRunRepository:
    """Repositório em memória de `AgentRunRecord` para testes e inspeção rápida."""

    def __init__(self) -> None:
        self.runs: list[AgentRunRecord] = []

    async def save_run(self, record: AgentRunRecord) -> None:
        self.runs.append(record)


class PostgresAgentRunRepository:
    """Repositório PostgreSQL que grava telemetria na tabela `agent_runs`."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def save_run(self, record: AgentRunRecord) -> None:
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO agent_runs (
                            id, queue_item_id, thread_id, agent_name,
                            llm_provider, llm_model, prompt_version,
                            prompt_tokens, completion_tokens, latency_ms,
                            guardrail_triggered, guardrail_reason, status, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            record.id,
                            record.queue_item_id,
                            record.thread_id,
                            record.agent_name,
                            record.llm_provider,
                            record.llm_model,
                            record.prompt_version,
                            record.prompt_tokens,
                            record.completion_tokens,
                            record.latency_ms,
                            record.guardrail_triggered,
                            record.guardrail_reason,
                            str(record.status),
                            record.created_at,
                        ),
                    )


# ==============================================================================
# 3. Extração Determinística + Sumarização de Dupla Memória (`T038`)
# ==============================================================================

_FACT_EXTRACTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "nome_cliente",
        re.compile(
            r"\b(?i:meu\s+nome\s+[eé]|me\s+chamo|sou\s+o|sou\s+a)\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)?)",
        ),
    ),
    (
        "empresa",
        re.compile(
            r"\b(?:trabalho\s+na|minha\s+empresa\s+[eé]\s+a?|sou\s+da\s+empresa)\s+([A-Za-zÀ-ÿ0-9_\-\s]{2,35}?)(?:[.,;!\n]|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "plano_interesse",
        re.compile(
            r"\b(?:interesse\s+no\s+plano|quero\s+o\s+plano|contratar\s+o\s+plano)\s+(starter|growth|enterprise)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "preferencia_contato",
        re.compile(
            r"\b(?:prefiro\s+contato\s+por|prefiro\s+atendimento\s+por|gosto\s+de)\s+([A-Za-zÀ-ÿ0-9\s]{3,30}?)(?:[.,;!\n]|$)",
            re.IGNORECASE,
        ),
    ),
)


def extract_semantic_facts_from_text(user_text: str) -> dict[str, str]:
    """Extrai fatos duráveis sobre o cliente a partir da mensagem de entrada (Memória Semântica)."""
    extracted: dict[str, str] = {}
    for fact_key, pattern in _FACT_EXTRACTORS:
        match = pattern.search(user_text)
        if match:
            val = match.group(1).strip(" .,;!")
            if val:
                extracted[fact_key] = val
    return extracted


def build_compact_summary(
    previous_summary: str,
    messages_to_summarize: list[dict[str, str]],
) -> str:
    """Compacta mensagens antigas em um resumo conciso de domínio gastando o mínimo de tokens."""
    highlights: list[str] = []
    if previous_summary.strip():
        highlights.append(previous_summary.strip())

    user_points = [
        m["content"].strip()
        for m in messages_to_summarize
        if m.get("role") == "user" and m.get("content")
    ]
    if user_points:
        joined_points = " | ".join(p[:100] for p in user_points[-6:])
        highlights.append(f"Tópicos abordados pelo cliente: {joined_points}")

    return " — ".join(highlights)


class ConversationMemoryMiddleware:
    """Gerencia a Dupla Memória (`thread_messages`, `conversation_summary` e `semantic_facts` — FR-014, T038)."""

    def __init__(
        self,
        threads_repo: ThreadsRepositoryProtocol,
        *,
        max_messages_before_summary: int = 12,
        keep_recent_after_summary: int = 2,
    ) -> None:
        self._repo = threads_repo
        self._max_messages = max(4, max_messages_before_summary)
        self._keep_recent = max(1, keep_recent_after_summary)

    async def invoke(
        self,
        context: MiddlewareContext,
        call_next: NextMiddlewareCallable,
    ) -> str:
        thread_key = str(context.thread_id)
        thread = await self._repo.get_or_create_thread(thread_key)

        # 1. Extrai e persiste novos fatos semânticos duráveis se presentes na mensagem atual
        new_facts = extract_semantic_facts_from_text(context.user_text)
        for fact_k, fact_v in new_facts.items():
            await self._repo.upsert_semantic_fact(thread_key, fact_k, fact_v)

        # 2. Carrega fatos semânticos, resumo acumulado e janela ativa para o contexto do grafo
        context.semantic_facts = await self._repo.get_semantic_facts(thread_key)
        context.conversation_summary = thread.conversation_summary
        active_msgs = await self._repo.get_active_messages(thread_key)
        context.conversation_history = [
            {"role": m.role, "content": m.content} for m in active_msgs
        ]

        # 3. Executa o grafo de cognição
        reply = await call_next(context)

        # 4. Se não houve bloqueio de Guardrail, salva o turno e verifica política de auto-sumarização
        if not context.guardrail_triggered:
            await self._repo.append_message(thread_key, "user", context.user_text)
            await self._repo.append_message(thread_key, "assistant", reply)

            updated_active = await self._repo.get_active_messages(thread_key)
            if len(updated_active) >= self._max_messages:
                older_slice = updated_active[: -self._keep_recent]
                new_summary = build_compact_summary(
                    thread.conversation_summary,
                    [{"role": m.role, "content": m.content} for m in older_slice],
                )
                await self._repo.compact_messages_with_summary(
                    thread_key,
                    new_summary,
                    keep_recent=self._keep_recent,
                )
                context.conversation_summary = new_summary

        return reply


# ==============================================================================
# 4. Implementações Concretas dos Middlewares (`Latency`, `TokenBudget`, `Audit`)
# ==============================================================================


class LatencyTrackingMiddleware:
    """Mede o tempo de execução do turno em milissegundos e popula `context.latency_ms`."""

    async def invoke(
        self,
        context: MiddlewareContext,
        call_next: NextMiddlewareCallable,
    ) -> str:
        start = time.perf_counter()
        try:
            return await call_next(context)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            context.latency_ms = max(1, elapsed_ms)


class TokenBudgetMiddleware:
    """Verifica o orçamento diário de tokens antes do turno e contabiliza o gasto ao final (FR-017)."""

    DEFAULT_EXCEEDED_REPLY = (
        "Você atingiu o limite diário de atendimento automático para hoje. "
        "Caso precise de ajuda urgente, um atendente humano poderá auxiliá-lo em breve."
    )

    def __init__(
        self,
        budget_store: TokenBudgetStoreProtocol,
        *,
        daily_limit: int = 50000,
        raise_on_exceeded: bool = False,
        exceeded_reply_text: str = DEFAULT_EXCEEDED_REPLY,
    ) -> None:
        self._store = budget_store
        self._daily_limit = daily_limit
        self._raise_on_exceeded = raise_on_exceeded
        self._exceeded_reply_text = exceeded_reply_text

    async def invoke(
        self,
        context: MiddlewareContext,
        call_next: NextMiddlewareCallable,
    ) -> str:
        thread_key = str(context.thread_id)
        used_before = await self._store.get_daily_tokens_used(thread_key)

        if used_before >= self._daily_limit:
            context.guardrail_triggered = True
            context.guardrail_reason = "daily_token_budget_exceeded"
            context.status = RunStatus.BLOCKED
            if self._raise_on_exceeded:
                raise TokenBudgetExceededError(
                    thread_id=thread_key,
                    tokens_used=used_before,
                    daily_limit=self._daily_limit,
                )
            return self._exceeded_reply_text

        reply = await call_next(context)
        turn_tokens = context.prompt_tokens + context.completion_tokens
        if turn_tokens > 0:
            await self._store.add_daily_tokens(thread_key, turn_tokens)
        return reply


class AuditRunMiddleware:
    """Constrói e persiste o `AgentRunRecord` ao término de cada execução do grafo."""

    def __init__(self, run_repo: AgentRunRepositoryProtocol) -> None:
        self._repo = run_repo

    async def invoke(
        self,
        context: MiddlewareContext,
        call_next: NextMiddlewareCallable,
    ) -> str:
        try:
            reply = await call_next(context)
            if context.guardrail_triggered:
                context.status = RunStatus.BLOCKED
            else:
                context.status = RunStatus.SUCCESS
            return reply
        except Exception as exc:
            context.status = RunStatus.FAILED
            if not context.guardrail_reason:
                context.guardrail_reason = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record = AgentRunRecord(
                queue_item_id=context.queue_item_id,
                thread_id=str(context.thread_id),
                agent_name=context.agent_name,
                llm_provider=context.llm_provider,
                llm_model=context.llm_model,
                prompt_version=context.prompt_version,
                prompt_tokens=context.prompt_tokens,
                completion_tokens=context.completion_tokens,
                latency_ms=context.latency_ms,
                guardrail_triggered=context.guardrail_triggered,
                guardrail_reason=context.guardrail_reason,
                status=context.status,
            )
            await self._repo.save_run(record)


class MiddlewarePipeline:
    """Encadeador de Middlewares em estilo *Russian Doll* / MediatR `IPipelineBehavior`."""

    def __init__(self, middlewares: list[CognitionMiddlewareProtocol] | None = None) -> None:
        self._middlewares: list[CognitionMiddlewareProtocol] = list(middlewares or [])

    def add(self, middleware: CognitionMiddlewareProtocol) -> "MiddlewarePipeline":
        self._middlewares.append(middleware)
        return self

    async def execute(
        self,
        context: MiddlewareContext,
        terminal_handler: NextMiddlewareCallable,
    ) -> str:
        """Executa todos os middlewares registrados na ordem de adição até o `terminal_handler`."""
        chain = terminal_handler
        for mw in reversed(self._middlewares):
            current_mw = mw
            next_in_chain = chain

            async def _step(
                ctx: MiddlewareContext,
                _mw: CognitionMiddlewareProtocol = current_mw,
                _next: NextMiddlewareCallable = next_in_chain,
            ) -> str:
                return await _mw.invoke(ctx, _next)

            chain = _step

        return await chain(context)
