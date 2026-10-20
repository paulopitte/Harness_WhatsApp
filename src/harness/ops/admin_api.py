"""API Administrativa e de Operação da Harness (`ops/admin_api.py` — FR-015, FR-018, FR-019, T048).

Processo 3 (`admin`): Isolado da Borda e dos Workers para permitir:
- Inspeção da fila (`GET /admin/queue/stats` e `GET /admin/stats`)
- Reprocessamento da Business DLQ (`POST /admin/queue/reprocess-dead` e `POST /admin/dlq/reprocess`)
- Handoff Humano (`PATCH /admin/threads/{thread_id}/mode` alternando `bot` | `human` | `paused`)
- Inspeção de Memória Semântica e Histórico (`GET /admin/threads/{thread_id}/facts`)
- Auditoria de Runs e Quarentena (`GET /admin/runs` e `GET /admin/quarantine`)
"""

from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from harness.domain.ports import CognitionEngineProtocol, QueueConsumerProtocol
from harness.domain.value_objects import QueueStatus, ThreadId, ThreadMode
from harness.ops.security import build_admin_api_key_dependency
from harness.persistence.runs_repo import RunsQueryRepositoryProtocol
from harness.persistence.threads_repo import ThreadsRepositoryProtocol
from harness.settings import HarnessSettings


class UpdateThreadModeRequest(BaseModel):
    """Payload de atualização do modo de atendimento da conversa (Handoff Humano — FR-015)."""

    mode: ThreadMode


class OperatorReplyRequest(BaseModel):
    """Mensagem enviada por atendente humano diretamente para a conversa."""

    text: str = Field(min_length=1)


class ReplayDlqItemRequest(BaseModel):
    """Payload para reprocessar mensagem da Dead Letter Queue."""

    id: str | None = None


class SimulatorChatRequest(BaseModel):
    """Payload para simulação síncrona de chat Request/Response via Postman/Swagger."""

    phone_number: str = Field(default="5511999998888", min_length=3)
    text: str = Field(min_length=1)


def create_admin_app(
    settings: HarnessSettings,
    queue_consumer: QueueConsumerProtocol,
    threads_repo: ThreadsRepositoryProtocol,
    runs_repo: RunsQueryRepositoryProtocol | None = None,
    cognition_engine: CognitionEngineProtocol | None = None,
) -> FastAPI:
    """Fábrica da aplicação FastAPI de Operação e Governança (`ops/admin_api.py`)."""
    app = FastAPI(
        title="WhatsApp Harness — Admin & Operations API",
        version="0.1.0",
        description="Painel HTTP de governança operacional, DLQ, Handoff Humano, Simulador Síncrono e telemetria.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    require_api_key = build_admin_api_key_dependency(settings.admin_api_key)
    admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_api_key)])

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "WhatsApp Harness — Admin & Operations API",
            "status": "running",
            "docs_url": "/docs",
            "health_url": "/health",
            "stats_url": "/admin/queue/stats",
            "simulator_url": "/admin/simulator/chat",
        }

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "component": "ops-admin"}

    @admin_router.post("/simulator/chat")
    async def simulate_synchronous_chat(body: SimulatorChatRequest) -> dict[str, Any]:
        """Simulador Síncrono (Request/Response Direto para Postman/Testes).

        Executa o motor de cognição completo (LangGraph + Guardrails + Dupla Memória + RAG + Langfuse)
        e devolve a resposta da IA diretamente no corpo do HTTP Response, sem precisar esperar o Worker!
        """
        thread_id = ThreadId(body.phone_number)
        thread = await threads_repo.get_or_create_thread(str(thread_id))
        if not thread.is_bot_active:
            await threads_repo.append_message(str(thread_id), "user", body.text)
            return {
                "thread_id": str(thread_id),
                "phone_number": body.phone_number,
                "mode": str(thread.mode),
                "user_text": body.text,
                "bot_reply": None,
                "note": f"Thread em modo '{thread.mode}' (Handoff Humano ativo). Mensagem salva no histórico sem acionar o bot.",
            }

        if cognition_engine is None:
            reply_text = f"[Simulador Admin] Recebi: {body.text}"
        else:
            reply_text = await cognition_engine.generate_reply(thread_id, body.text)

        updated_thread = await threads_repo.get_or_create_thread(str(thread_id))
        facts = await threads_repo.get_semantic_facts(str(thread_id))
        return {
            "thread_id": str(thread_id),
            "phone_number": body.phone_number,
            "mode": str(updated_thread.mode),
            "provider": settings.cognition.llm.provider,
            "model": settings.cognition.llm.model,
            "user_text": body.text,
            "bot_reply": reply_text,
            "conversation_summary": updated_thread.conversation_summary,
            "semantic_facts": facts,
        }

    @admin_router.get("/queue/stats")
    @admin_router.get("/stats")
    async def get_queue_stats() -> dict[str, int]:
        """Retorna a contagem de itens por estado (`pending`, `processing`, `done`, `dead`, `quarantined_inbound`)."""
        stats = await queue_consumer.get_stats()
        return stats.model_dump()

    @admin_router.post("/queue/reprocess-dead")
    @admin_router.post("/dlq/reprocess")
    async def reprocess_dead_queue_items() -> dict[str, Any]:
        """Move todos os itens em `dead` (Business DLQ) de volta para `pending` com `attempts = 0`."""
        count = await queue_consumer.reprocess_dead_items()
        return {"status": "requeued", "reprocessed_count": count}

    @admin_router.patch("/threads/{thread_id}/mode")
    async def update_thread_mode(
        thread_id: str,
        body: UpdateThreadModeRequest,
    ) -> dict[str, Any]:
        """Altera o modo da thread entre `bot`, `human` e `paused` (Handoff Humano — FR-015)."""
        normalized_id = str(ThreadId(thread_id))
        updated_thread = await threads_repo.set_thread_mode(normalized_id, body.mode)
        return {
            "thread_id": updated_thread.thread_id,
            "phone_number": updated_thread.phone_number,
            "mode": str(updated_thread.mode),
            "is_bot_active": updated_thread.is_bot_active,
        }

    @admin_router.get("/threads/{thread_id}/facts")
    async def get_thread_memory_and_facts(thread_id: str) -> dict[str, Any]:
        """Consulta a Dupla Memória (`conversation_summary`, `semantic_facts` e janela ativa) de um cliente."""
        normalized_id = str(ThreadId(thread_id))
        thread = await threads_repo.get_or_create_thread(normalized_id)
        facts = await threads_repo.get_semantic_facts(normalized_id)
        active_msgs = await threads_repo.get_active_messages(normalized_id)
        return {
            "thread_id": thread.thread_id,
            "phone_number": thread.phone_number,
            "mode": str(thread.mode),
            "conversation_summary": thread.conversation_summary,
            "semantic_facts": facts,
            "active_messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in active_msgs
            ],
        }

    @admin_router.get("/runs")
    async def list_recent_agent_runs(limit: int = 50) -> dict[str, Any]:
        """Lista os registros recentes de execução do motor de cognição (`agent_runs`)."""
        if runs_repo is None:
            return {"runs": []}
        runs = await runs_repo.list_recent_runs(limit=limit)
        return {"runs": [r.model_dump(mode="json") for r in runs]}

    @admin_router.get("/health")
    async def admin_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "component": "ops-admin",
            "version": "0.1.0",
            "database": "postgres-connected",
            "llm_provider": settings.cognition.llm.provider,
        }

    @admin_router.post("/threads/{thread_id}/handoff")
    async def set_thread_handoff(
        thread_id: str,
        body: UpdateThreadModeRequest,
    ) -> dict[str, Any]:
        """Alterna o modo da thread entre `bot`, `human` e `paused` (Handoff Humano — FR-015)."""
        normalized_id = str(ThreadId(thread_id))
        updated_thread = await threads_repo.set_thread_mode(normalized_id, body.mode)
        return {
            "status": "success",
            "thread_id": updated_thread.thread_id,
            "phone_number": updated_thread.phone_number,
            "mode": str(updated_thread.mode),
            "is_bot_active": updated_thread.is_bot_active,
        }

    @admin_router.post("/threads/{thread_id}/reply")
    async def send_operator_reply(
        thread_id: str,
        body: OperatorReplyRequest,
    ) -> dict[str, Any]:
        """Envia mensagem manual de atendente humano para a conversa."""
        normalized_id = str(ThreadId(thread_id))
        msg = await threads_repo.append_message(normalized_id, "assistant", body.text)
        return {
            "status": "sent",
            "message_id": str(msg.id),
            "thread_id": normalized_id,
            "role": "assistant",
            "content": body.text,
        }

    @admin_router.get("/threads")
    async def list_threads(limit: int = 50) -> list[dict[str, Any]]:
        """Lista threads recentes com última mensagem e modo atual."""
        threads = await threads_repo.list_threads(limit=limit)
        results: list[dict[str, Any]] = []
        for t in threads:
            msgs = await threads_repo.get_active_messages(t.thread_id)
            last_msg = msgs[-1].content if msgs else (t.conversation_summary or "")
            results.append(
                {
                    "id": t.thread_id,
                    "phone_number": t.phone_number,
                    "mode": str(t.mode),
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat(),
                    "last_message": last_msg,
                }
            )
        return results

    @admin_router.get("/threads/{thread_id}/messages")
    async def list_thread_messages(thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Histórico completo de mensagens de uma conversa para o chat."""
        normalized_id = str(ThreadId(thread_id))
        msgs = await threads_repo.get_all_messages(normalized_id, limit=limit)
        return [
            {
                "id": str(m.id),
                "thread_id": m.thread_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ]

    @admin_router.get("/queue/items")
    async def list_queue_items(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Lista itens da fila operacional com paginação e filtro de status."""
        target_status = QueueStatus(status) if status else None
        items = await queue_consumer.list_items(status=target_status, limit=limit)
        return [
            {
                "id": str(i.id),
                "thread_id": i.thread_id,
                "phone_number": i.phone_number,
                "status": str(i.status),
                "retry_count": i.attempts,
                "max_retries": i.max_retries,
                "error_message": i.last_error,
                "scheduled_for": i.scheduled_for.isoformat(),
                "created_at": i.created_at.isoformat(),
            }
            for i in items
        ]

    @admin_router.post("/queue/dlq/replay")
    async def replay_dlq(body: ReplayDlqItemRequest | None = None) -> dict[str, Any]:
        """Reprocessa mensagens da Dead Letter Queue."""
        count = await queue_consumer.reprocess_dead_items()
        return {"status": "requeued", "reprocessed_count": count}

    @admin_router.get("/audit/logs")
    async def list_audit_logs(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Lista logs de auditoria e intervenções dos guardrails de segurança."""
        if runs_repo is None:
            return []
        runs = await runs_repo.list_recent_runs(limit=limit)
        return [
            {
                "id": str(r.id),
                "thread_id": r.thread_id,
                "status": str(r.status),
                "latency_ms": r.latency_ms,
                "tokens_used": r.total_tokens,
                "blocked_reason": r.guardrail_reason if str(r.status) == "blocked" else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
            if not status or str(r.status) == status
        ]

    @admin_router.get("/agents/config")
    async def get_agent_config() -> dict[str, Any]:
        """Retorna parâmetros e status das ferramentas do agente cognitivo."""
        return {
            "default_prompt_name": settings.prompts.default_prompt_name,
            "deep_research_enabled": settings.deep_research.enabled,
            "website_crawler_enabled": settings.website_crawler.enabled,
            "model_provider": settings.cognition.llm.provider,
            "model_name": settings.cognition.llm.model,
            "temperature": settings.cognition.llm.temperature,
        }

    @admin_router.post("/agents/config")
    async def update_agent_config(body: dict[str, Any]) -> dict[str, Any]:
        """Atualiza flags e configurações dinâmicas de cognição."""
        if "deep_research_enabled" in body:
            settings.deep_research.enabled = bool(body["deep_research_enabled"])
        if "website_crawler_enabled" in body:
            settings.website_crawler.enabled = bool(body["website_crawler_enabled"])
        return {"status": "saved", "config": await get_agent_config()}

    @admin_router.get("/quarantine")
    async def list_quarantine_inbound(limit: int = 50) -> dict[str, Any]:
        """Lista os payloads inválidos barrados na Quarentena de Borda (`quarantine_inbound`)."""
        if runs_repo is None:
            return {"quarantine_entries": []}
        entries = await runs_repo.list_quarantine_entries(limit=limit)
        return {"quarantine_entries": [e.model_dump(mode="json") for e in entries]}

    app.include_router(admin_router)
    return app


