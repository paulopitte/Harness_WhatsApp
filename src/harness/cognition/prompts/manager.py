"""Gerenciador de Prompts Versionados (PromptOps) com Langfuse e Fallback YAML Local (`cognition/prompts/manager.py` — FR-021, T044).

Equivalente no C#/.NET: `IPromptProvider` com `IMemoryCache` (TTL configurável) e política de Fallback (`Polly` FallbackPolicy)
que lê de `configs/prompts/{prompt_name}.yaml` caso o servidor Langfuse esteja indisponível ou desabilitado.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from harness.settings import HarnessSettings, PromptsConfig


@runtime_checkable
class LangfusePromptClientProtocol(Protocol):
    """Interface mínima de cliente Langfuse para busca de prompts remotos (facilita injeção e mocks)."""

    def get_prompt(self, name: str, *, label: str = "production") -> Any: ...


@dataclass(frozen=True, slots=True)
class CachedPromptEntry:
    """Entrada armazenada no cache em memória com timestamp de expiração."""

    raw_template: str
    version: str
    expires_at: float


class PromptManager:
    """Implementação oficial de `PromptProviderPort` com Cache TTL e Fallback YAML Local (FR-021)."""

    def __init__(
        self,
        prompts_config: PromptsConfig | None = None,
        *,
        settings: HarnessSettings | None = None,
        langfuse_client: LangfusePromptClientProtocol | None = None,
    ) -> None:
        self._cfg = prompts_config or (settings.prompts if settings else PromptsConfig())
        self._settings = settings
        self._langfuse_client = langfuse_client
        self._cache: dict[str, CachedPromptEntry] = {}

    def invalidate_cache(self) -> None:
        """Limpa o cache em memória de prompts."""
        self._cache.clear()

    def _get_or_init_langfuse_client(self) -> LangfusePromptClientProtocol | None:
        if self._langfuse_client is not None:
            return self._langfuse_client
        if self._cfg.provider == "local_only":
            return None
        if self._settings is None:
            return None
        if not (self._settings.langfuse_public_key and self._settings.langfuse_secret_key):
            return None
        try:
            from langfuse import Langfuse

            self._langfuse_client = Langfuse(
                public_key=self._settings.langfuse_public_key,
                secret_key=self._settings.langfuse_secret_key,
                host=self._settings.langfuse_host,
            )
            return self._langfuse_client
        except Exception:
            return None

    def _load_local_yaml(self, prompt_name: str) -> tuple[str, str]:
        """Carrega o arquivo YAML local correspondente a `prompt_name` em `configs/prompts/`."""
        prompts_dir = Path(self._cfg.local_prompts_dir)
        yaml_path = prompts_dir / f"{prompt_name}.yaml"
        if yaml_path.exists():
            with yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                template = str(
                    data.get(
                        "template",
                        "Você é o assistente virtual oficial de atendimento via WhatsApp.",
                    )
                )
                version = str(data.get("version", "local-1.0.0"))
                return template, version

        return (
            "Você é o assistente virtual oficial de atendimento via WhatsApp.\n"
            "Fatos do cliente: {semantic_facts}\nResumo: {conversation_summary}",
            "local-fallback-1.0.0",
        )

    @staticmethod
    def _render_variables(raw_template: str, variables: dict[str, str] | None) -> str:
        rendered = raw_template
        if not variables:
            return rendered
        for k, v in variables.items():
            # Suporta tanto sintaxe Python/YAML `{var}` quanto sintaxe Mustache do Langfuse `{{var}}`
            rendered = rendered.replace(f"{{{{{k}}}}}", str(v)).replace(f"{{{k}}}", str(v))
        return rendered

    async def get_system_prompt(
        self,
        prompt_name: str,
        label: str = "production",
        variables: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Busca o prompt compilado e sua versão (`langfuse-vX` ou `local-1.0.0`) respeitando o cache TTL."""
        effective_label = label or self._cfg.default_label
        cache_key = f"{prompt_name}:{effective_label}"
        now = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None and now < cached.expires_at:
            return self._render_variables(cached.raw_template, variables), cached.version

        raw_template: str | None = None
        version: str | None = None

        if self._cfg.provider == "local_with_langfuse":
            client = self._get_or_init_langfuse_client()
            if client is not None:
                try:
                    remote_prompt = client.get_prompt(prompt_name, label=effective_label)
                    raw_template = str(
                        getattr(remote_prompt, "prompt", "") or remote_prompt
                    )
                    remote_ver = getattr(remote_prompt, "version", 1)
                    version = f"langfuse-v{remote_ver}"
                except Exception:
                    raw_template = None
                    version = None

        if not raw_template or not version:
            raw_template, version = self._load_local_yaml(prompt_name)

        ttl = max(0, self._cfg.cache_ttl_seconds)
        if ttl > 0:
            self._cache[cache_key] = CachedPromptEntry(
                raw_template=raw_template,
                version=version,
                expires_at=now + ttl,
            )

        return self._render_variables(raw_template, variables), version

