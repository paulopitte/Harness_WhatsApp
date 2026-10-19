"""Motor de Cognição em LangGraph (`cognition/graph.py` — FR-010, FR-011, FR-012, T034).

Equivalente no C#/.NET: Máquina de Estados / Orquestrador (`SemanticKernel` Process Framework ou `Stateless`)
envolto por `MiddlewarePipeline` (MediatR `IPipelineBehavior`).
Compila um `StateGraph` determinístico:
`START -> input_guardrail -> (bloqueado? END : prepare_context -> invoke_llm -> output_guardrail -> END)`.
"""

from pathlib import Path
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
import yaml

from harness.cognition.factory import ChatModelAdapterProtocol
from harness.cognition.guardrails import (
    DEFAULT_BLOCKED_REPLY,
    input_guardrail_node,
    output_guardrail_node,
)
from harness.cognition.middlewares import MiddlewareContext, MiddlewarePipeline
from harness.domain.ports import PromptProviderPort, RetrieverPort
from harness.domain.value_objects import ThreadId
from harness.settings import GuardrailsConfig


class AgentGraphState(TypedDict, total=False):
    """Estado tipado trafegado entre os nós do `StateGraph` do LangGraph."""

    thread_id: str
    user_text: str
    system_prompt: str
    prompt_version: str
    rag_context: list[str]
    conversation_history: list[dict[str, str]]
    conversation_summary: str
    semantic_facts: dict[str, str]
    guardrails_enabled: bool
    block_prompt_injection: bool
    blocked_reply_text: str
    guardrail_triggered: bool
    guardrail_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    final_reply: str


def _load_default_local_prompt(prompt_yaml_path: str = "configs/prompts/default_agent.yaml") -> tuple[str, str]:
    """Carrega o template YAML local padrão caso nenhum `PromptProviderPort` tenha sido injetado."""
    path = Path(prompt_yaml_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            template = str(data.get("template", "Você é um assistente prestativo via WhatsApp."))
            version = str(data.get("version", "local-1.0.0"))
            return template, version
    return (
        "Você é o assistente virtual oficial de atendimento via WhatsApp. "
        "Responda em português do Brasil de forma cordial e objetiva.",
        "local-1.0.0",
    )


class LangGraphCognitionEngine:
    """Motor principal de cognição compilado com `StateGraph` e protegido por Guardrails e Middlewares."""

    def __init__(
        self,
        model_adapter: ChatModelAdapterProtocol,
        *,
        middleware_pipeline: MiddlewarePipeline | None = None,
        guardrails_config: GuardrailsConfig | None = None,
        retriever: RetrieverPort | None = None,
        prompt_provider: PromptProviderPort | None = None,
        agent_name: str = "default_agent",
    ) -> None:
        self._model = model_adapter
        self._pipeline = middleware_pipeline or MiddlewarePipeline()
        self._guardrails_cfg = guardrails_config or GuardrailsConfig()
        self._retriever = retriever
        self._prompt_provider = prompt_provider
        self._agent_name = agent_name
        self._compiled_graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Constrói e compila o `StateGraph` do LangGraph."""
        workflow: StateGraph[Any] = StateGraph(AgentGraphState)

        workflow.add_node("input_guardrail", input_guardrail_node)
        workflow.add_node("prepare_context", self._prepare_context_node)
        workflow.add_node("invoke_llm", self._invoke_llm_node)
        workflow.add_node("output_guardrail", output_guardrail_node)

        workflow.add_edge(START, "input_guardrail")
        workflow.add_conditional_edges(
            "input_guardrail",
            self._route_after_input_guardrail,
            {
                "blocked": END,
                "allowed": "prepare_context",
            },
        )
        workflow.add_edge("prepare_context", "invoke_llm")
        workflow.add_edge("invoke_llm", "output_guardrail")
        workflow.add_edge("output_guardrail", END)

        return workflow.compile()

    @staticmethod
    def _route_after_input_guardrail(state: AgentGraphState) -> str:
        """Desvia imediatamente para `END` quando o Input Guardrail detecta Prompt Injection."""
        if state.get("guardrail_triggered"):
            return "blocked"
        return "allowed"

    async def _prepare_context_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Recupera o System Prompt (PromptOps/YAML) e o contexto institucional via RAG se disponíveis."""
        user_text = state.get("user_text", "")
        summary = state.get("conversation_summary", "Sem histórico anterior resumido.")
        facts_dict = state.get("semantic_facts") or {}
        facts_str = (
            ", ".join(f"{k}: {v}" for k, v in facts_dict.items())
            if facts_dict
            else "Nenhum fato semântico registrado ainda."
        )

        if self._prompt_provider is not None:
            system_prompt, prompt_version = await self._prompt_provider.get_system_prompt(
                prompt_name=self._agent_name,
                variables={
                    "semantic_facts": facts_str,
                    "conversation_summary": summary,
                },
            )
        else:
            raw_template, prompt_version = _load_default_local_prompt()
            system_prompt = raw_template.replace("{semantic_facts}", facts_str).replace(
                "{conversation_summary}", summary
            )

        rag_chunks: list[str] = []
        if self._retriever is not None and user_text.strip():
            rag_chunks = await self._retriever.retrieve_context(user_text)
            if rag_chunks:
                joined_rag = "\n- ".join(rag_chunks)
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"## Contexto Institucional Recuperado (RAG):\n- {joined_rag}"
                )

        return {
            "system_prompt": system_prompt,
            "prompt_version": prompt_version,
            "rag_context": rag_chunks,
        }

    async def _invoke_llm_node(self, state: AgentGraphState) -> dict[str, Any]:
        """Invoca o adaptador de modelo LLM agnóstico (`Gemini`, `OpenAI` ou `Ollama`)."""
        system_prompt = state.get("system_prompt", "")
        user_text = state.get("user_text", "")
        history = state.get("conversation_history") or []

        completion = await self._model.ainvoke_messages(
            system_prompt=system_prompt,
            user_message=user_text,
            conversation_history=history,
        )
        return {
            "final_reply": completion.content,
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
        }

    async def generate_reply(
        self,
        thread_id: ThreadId,
        user_text: str,
        queue_item_id: UUID | None = None,
    ) -> str:
        """Executa o pipeline completo de Middlewares + Grafo LangGraph (`CognitionEngineProtocol`)."""
        context = MiddlewareContext(
            thread_id=thread_id,
            user_text=user_text,
            queue_item_id=queue_item_id,
            agent_name=self._agent_name,
            llm_provider=self._model.provider_name,
            llm_model=self._model.model_name,
        )

        async def _run_graph(ctx: MiddlewareContext) -> str:
            initial_state: AgentGraphState = {
                "thread_id": str(ctx.thread_id),
                "user_text": ctx.user_text,
                "guardrails_enabled": self._guardrails_cfg.enabled,
                "block_prompt_injection": self._guardrails_cfg.block_prompt_injection,
                "blocked_reply_text": self._guardrails_cfg.blocked_reply_text or DEFAULT_BLOCKED_REPLY,
                "guardrail_triggered": False,
                "guardrail_reason": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "final_reply": "",
            }
            result_state: dict[str, Any] = await self._compiled_graph.ainvoke(initial_state)

            ctx.prompt_version = str(result_state.get("prompt_version", ctx.prompt_version))
            ctx.prompt_tokens = int(result_state.get("prompt_tokens", 0))
            ctx.completion_tokens = int(result_state.get("completion_tokens", 0))
            ctx.guardrail_triggered = bool(result_state.get("guardrail_triggered", False))
            ctx.guardrail_reason = result_state.get("guardrail_reason")

            return str(result_state.get("final_reply", "")).strip()

        return await self._pipeline.execute(context, _run_graph)

