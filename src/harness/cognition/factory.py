"""Fábrica Agnóstica de Modelos LLM (`cognition/factory.py` — FR-012, T031).

Equivalente no C#/.NET: Abstract Factory / `IChatClient` (`Microsoft.Extensions.AI`)
que instancia o provedor configurado (`gemini`, `openai` ou `ollama`) a partir de `HarnessSettings`,
sem exigir alteração de código nos nós do grafo LangGraph (SOLID OCP & DIP).
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from harness.settings import HarnessSettings, LlmConfig


@dataclass(frozen=True, slots=True)
class LlmCompletionResult:
    """Resultado padronizado de uma invocação de modelo LLM com metadados de tokens."""

    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_name: str = ""
    provider_name: str = ""


@runtime_checkable
class ChatModelAdapterProtocol(Protocol):
    """Porta agnóstica para invocação assíncrona de modelos de chat no motor de cognição."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def ainvoke_messages(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> LlmCompletionResult:
        """Invoca o modelo LLM com prompt de sistema, histórico e mensagem atual."""
        ...


class LangChainChatModelAdapter:
    """Adaptador envolvendo um `BaseChatModel` do LangChain v1 (`ChatGoogleGenerativeAI`, `ChatOpenAI`, `ChatOllama`)."""

    def __init__(
        self,
        lc_model: Any,
        *,
        provider_name: str,
        model_name: str,
    ) -> None:
        self._lc_model = lc_model
        self._provider_name = provider_name
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def ainvoke_messages(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> LlmCompletionResult:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages: list[Any] = [SystemMessage(content=system_prompt)]
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "assistant":
                    messages.append(AIMessage(content=content))
                elif role == "system":
                    messages.append(SystemMessage(content=content))
                else:
                    messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=user_message))

        response = await self._lc_model.ainvoke(messages)
        text_content = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )

        # Extrai contagem de tokens de usage_metadata (padrão LangChain v1) ou estima por palavras
        usage = getattr(response, "usage_metadata", None) or {}
        prompt_tokens = int(usage.get("input_tokens", max(1, len(system_prompt.split()) + len(user_message.split()))))
        completion_tokens = int(usage.get("output_tokens", max(1, len(text_content.split()))))

        return LlmCompletionResult(
            content=text_content.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=self._model_name,
            provider_name=self._provider_name,
        )


class DeterministicStubChatModelAdapter:
    """Adaptador determinístico usado quando nenhuma chave de API está configurada em ambiente de teste/dev."""

    def __init__(self, *, provider_name: str, model_name: str) -> None:
        self._provider_name = provider_name
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def ainvoke_messages(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> LlmCompletionResult:
        history_len = len(conversation_history) if conversation_history else 0
        reply = (
            f"[{self._provider_name}:{self._model_name}] "
            f"Recebi sua mensagem: '{user_message}'. "
            f"(Contexto ativo: {history_len} msgs)."
        )
        prompt_tokens = max(10, len(system_prompt.split()) + len(user_message.split()))
        completion_tokens = max(8, len(reply.split()))
        return LlmCompletionResult(
            content=reply,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=self._model_name,
            provider_name=self._provider_name,
        )


class ModelFactory:
    """Fábrica agnóstica de modelos LLM (`gemini`, `openai`, `ollama` — FR-012)."""

    SUPPORTED_PROVIDERS = ("gemini", "openai", "ollama")

    @classmethod
    def create(
        cls,
        llm_config: LlmConfig,
        settings: HarnessSettings | None = None,
        *,
        allow_stub_fallback: bool = True,
    ) -> ChatModelAdapterProtocol:
        """Instancia o adaptador do provedor configurado em `LlmConfig`."""
        provider = llm_config.provider.lower().strip()
        if provider not in cls.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provedor LLM '{provider}' não suportado. Use um de: {cls.SUPPORTED_PROVIDERS}"
            )

        google_key = settings.google_api_key if settings else ""
        openai_key = settings.openai_api_key if settings else ""
        ollama_url = settings.ollama_base_url if settings else "http://localhost:11434"

        if provider == "gemini":
            if not google_key and allow_stub_fallback:
                return DeterministicStubChatModelAdapter(
                    provider_name="gemini",
                    model_name=llm_config.model,
                )
            from langchain_google_genai import ChatGoogleGenerativeAI

            lc_gemini = ChatGoogleGenerativeAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_output_tokens=llm_config.max_tokens,
                google_api_key=google_key or "missing-api-key",
            )
            return LangChainChatModelAdapter(
                lc_gemini,
                provider_name="gemini",
                model_name=llm_config.model,
            )

        if provider == "openai":
            if not openai_key and allow_stub_fallback:
                return DeterministicStubChatModelAdapter(
                    provider_name="openai",
                    model_name=llm_config.model,
                )
            from langchain_openai import ChatOpenAI

            lc_openai = ChatOpenAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                api_key=openai_key or "missing-api-key",  # type: ignore[arg-type]
            )
            return LangChainChatModelAdapter(
                lc_openai,
                provider_name="openai",
                model_name=llm_config.model,
            )

        # provider == "ollama"
        if allow_stub_fallback and (settings is None or settings.harness_env == "test"):
            return DeterministicStubChatModelAdapter(
                provider_name="ollama",
                model_name=llm_config.model,
            )
        from langchain_ollama import ChatOllama

        lc_ollama = ChatOllama(
            model=llm_config.model,
            temperature=llm_config.temperature,
            num_predict=llm_config.max_tokens,
            base_url=ollama_url,
        )
        return LangChainChatModelAdapter(
            lc_ollama,
            provider_name="ollama",
            model_name=llm_config.model,
        )

