"""Testes Unitários de PromptOps (`PromptManager`): Cache TTL, Langfuse e Fallback YAML Local (`T042`)."""

from dataclasses import dataclass

import pytest

from harness.cognition.factory import ModelFactory
from harness.cognition.graph import LangGraphCognitionEngine
from harness.cognition.middlewares import (
    AuditRunMiddleware,
    InMemoryAgentRunRepository,
    MiddlewarePipeline,
)
from harness.cognition.prompts.manager import PromptManager
from harness.domain.value_objects import ThreadId
from harness.settings import HarnessSettings, LlmConfig, PromptsConfig


@dataclass
class FakeLangfusePromptObject:
    prompt: str
    version: int


class FakeLangfuseClient:
    """Dublê de cliente Langfuse que conta chamadas de rede e permite simular queda."""

    def __init__(self, *, should_fail: bool = False, version: int = 3) -> None:
        self.should_fail = should_fail
        self.version = version
        self.calls = 0

    def get_prompt(self, name: str, *, label: str = "production") -> FakeLangfusePromptObject:
        self.calls += 1
        if self.should_fail:
            raise ConnectionError("Langfuse Cloud API indisponível (timeout simulado)")
        return FakeLangfusePromptObject(
            prompt=(
                f"[Prompt Remoto Langfuse ({label})] "
                "Fatos: {{semantic_facts}} | Resumo: {{conversation_summary}}"
            ),
            version=self.version,
        )


@pytest.mark.asyncio
async def test_prompt_manager_fetches_from_langfuse_and_uses_ttl_cache() -> None:
    """Valida busca por label/versão no Langfuse, substituição de variáveis e hit no cache TTL (FR-021)."""
    fake_client = FakeLangfuseClient(should_fail=False, version=4)
    cfg = PromptsConfig(
        provider="local_with_langfuse",
        default_prompt_name="default_agent",
        default_label="production",
        cache_ttl_seconds=300,
    )
    manager = PromptManager(cfg, langfuse_client=fake_client)

    compiled_1, ver_1 = await manager.get_system_prompt(
        "default_agent",
        label="production",
        variables={
            "semantic_facts": "nome_cliente: Ana",
            "conversation_summary": "Cliente perguntou sobre planos.",
        },
    )
    assert ver_1 == "langfuse-v4"
    assert "nome_cliente: Ana" in compiled_1
    assert "Cliente perguntou sobre planos." in compiled_1
    assert fake_client.calls == 1

    # Segunda chamada dentro do TTL deve vir 100% da memória sem nova chamada de rede ao Langfuse
    compiled_2, ver_2 = await manager.get_system_prompt(
        "default_agent",
        label="production",
        variables={
            "semantic_facts": "nome_cliente: Bruno",
            "conversation_summary": "Novo resumo.",
        },
    )
    assert ver_2 == "langfuse-v4"
    assert "nome_cliente: Bruno" in compiled_2
    assert fake_client.calls == 1


@pytest.mark.asyncio
async def test_prompt_manager_falls_back_to_local_yaml_when_langfuse_fails() -> None:
    """Garante resiliência 100% (SC-009): se o Langfuse falhar, carrega `configs/prompts/default_agent.yaml`."""
    failing_client = FakeLangfuseClient(should_fail=True)
    cfg = PromptsConfig(
        provider="local_with_langfuse",
        default_prompt_name="default_agent",
        cache_ttl_seconds=60,
        local_prompts_dir="configs/prompts",
    )
    manager = PromptManager(cfg, langfuse_client=failing_client)

    compiled, version = await manager.get_system_prompt(
        "default_agent",
        variables={
            "semantic_facts": "empresa: Acme",
            "conversation_summary": "Sem histórico.",
        },
    )
    assert version == "local-1.0.0"
    assert "Diretrizes Obrigatórias de Atendimento" in compiled
    assert "empresa: Acme" in compiled


@pytest.mark.asyncio
async def test_langgraph_records_prompt_version_in_agent_run_record() -> None:
    """Valida que a versão exata do prompt (`langfuse-v7`) é gravada na auditoria (`AgentRunRecord`)."""
    settings = HarnessSettings(harness_env="test")
    fake_client = FakeLangfuseClient(should_fail=False, version=7)
    prompt_manager = PromptManager(
        PromptsConfig(provider="local_with_langfuse", cache_ttl_seconds=60),
        langfuse_client=fake_client,
    )
    run_repo = InMemoryAgentRunRepository()
    model = ModelFactory.create(LlmConfig(provider="gemini", model="gemini-2.5-flash"), settings=settings)

    engine = LangGraphCognitionEngine(
        model_adapter=model,
        middleware_pipeline=MiddlewarePipeline([AuditRunMiddleware(run_repo)]),
        prompt_provider=prompt_manager,
    )

    await engine.generate_reply(ThreadId("wa:5511911112222"), "Olá, preciso de atendimento.")
    assert len(run_repo.runs) == 1
    assert run_repo.runs[0].prompt_version == "langfuse-v7"

