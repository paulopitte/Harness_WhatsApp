"""Configuração Hierárquica Tipada da WhatsApp Harness (Princípio VIII da Constitution).

Equivalente no C#/.NET: `IOptions<HarnessSettings>` combinando `appsettings.json` + Variáveis de Ambiente.
Lê `configs/harness.yaml` e permite sobrescrita via `.env` ou variáveis de ambiente do sistema operacional.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class AppConfig(BaseModel):
    name: str = "whatsapp-harness-mvp"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    admin_host: str = "0.0.0.0"
    admin_port: int = 8001


class EdgeMediaConfig(BaseModel):
    audio_enabled: bool = True
    image_enabled: bool = True
    unsupported_reply_text: str = (
        "Desculpe, no momento só consigo processar mensagens de texto, áudio ou imagem. "
        "Poderia escrever sua dúvida?"
    )


class EdgeConfig(BaseModel):
    verify_signature: bool = False
    fast_retry_attempts: int = Field(default=3, ge=1, le=10)
    fast_retry_initial_wait_ms: int = Field(default=50, ge=10, le=5000)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_max_messages: int = Field(default=20, ge=1)
    media: EdgeMediaConfig = Field(default_factory=EdgeMediaConfig)


class QueueConfig(BaseModel):
    provider: Literal["postgres", "in_memory"] = "postgres"
    debounce_seconds: float = Field(default=3.0, ge=0.0, le=60.0)
    max_retries: int = Field(default=3, ge=1, le=20)
    retry_base_backoff_seconds: float = Field(default=5.0, ge=0.1)
    worker_poll_interval_seconds: float = Field(default=0.5, ge=0.05)
    worker_concurrency: int = Field(default=4, ge=1, le=64)


class LlmConfig(BaseModel):
    provider: Literal["gemini", "openai", "ollama"] = "gemini"
    model: str = "gemini-2.5-flash"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64)


class CognitionConfig(BaseModel):
    agent_mode: Literal["echo", "langgraph"] = "echo"
    context_max_messages_before_summary: int = Field(default=12, ge=4)
    daily_token_budget_per_thread: int = Field(default=50000, ge=100)
    llm: LlmConfig = Field(default_factory=LlmConfig)


class GuardrailsConfig(BaseModel):
    enabled: bool = True
    mask_pii_at_edge: bool = True
    block_prompt_injection: bool = True
    blocked_reply_text: str = (
        "Desculpe, não posso atender a essa solicitação. "
        "Posso ajudar com dúvidas sobre nossos produtos, serviços ou suporte?"
    )


class RagConfig(BaseModel):
    enabled: bool = True
    provider: Literal["postgres", "qdrant", "in_memory"] = "postgres"
    collection_name: str = "company_knowledge"
    embedding_model: str = "models/text-embedding-004"
    top_k: int = Field(default=4, ge=1, le=20)


class PromptsConfig(BaseModel):
    provider: Literal["local_with_langfuse", "local_only"] = "local_with_langfuse"
    default_prompt_name: str = "default_agent"
    default_label: str = "production"
    cache_ttl_seconds: int = Field(default=300, ge=0)
    local_prompts_dir: str = "configs/prompts"


class OutboundConfig(BaseModel):
    provider: Literal["console", "meta"] = "console"
    meta_api_version: str = "v21.0"
    timeout_seconds: float = Field(default=10.0, ge=1.0)


class ObservabilityConfig(BaseModel):
    log_level: str = "INFO"
    json_logs: bool = False
    langfuse_enabled: bool = False
    otel_enabled: bool = True


class HarnessSettings(BaseSettings):
    """Configuração global carregando `configs/harness.yaml` + variáveis de ambiente (`.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Segredos e variáveis de ambiente de infraestrutura
    harness_env: str = Field(default="development")
    harness_config_path: str = Field(default="configs/harness.yaml")
    database_url: str = Field(
        default="postgresql://harness:harness_secret@localhost:5432/whatsapp_harness"
    )
    whatsapp_verify_token: str = Field(default="dev_verify_token_123")
    whatsapp_app_secret: str = Field(default="dev_app_secret_change_in_prod")
    whatsapp_access_token: str = Field(default="")
    whatsapp_phone_number_id: str = Field(default="")
    admin_api_key: str = Field(default="dev_admin_api_key_change_in_prod")

    google_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    ollama_base_url: str = Field(default="http://localhost:11434")

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")

    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")
    otel_service_name: str = Field(default="whatsapp-harness")

    # Seções estruturadas do YAML
    app: AppConfig = Field(default_factory=AppConfig)
    edge: EdgeConfig = Field(default_factory=EdgeConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    cognition: CognitionConfig = Field(default_factory=CognitionConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    outbound: OutboundConfig = Field(default_factory=OutboundConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def load(cls, yaml_path: str | Path | None = None) -> "HarnessSettings":
        """Carrega o YAML base e aplica overrides das variáveis de ambiente."""
        base_env = cls()
        target_path = Path(yaml_path or base_env.harness_config_path)
        yaml_data: dict[str, Any] = {}
        if target_path.exists():
            with target_path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    yaml_data = loaded
        return cls(**yaml_data)


@lru_cache(maxsize=1)
def get_settings() -> HarnessSettings:
    """Singleton de leitura rápida das configurações da aplicação."""
    return HarnessSettings.load()

