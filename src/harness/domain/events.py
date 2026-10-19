"""Modelos de Eventos Operacionais, Telemetria de Execução (`AgentRunRecord`) e Estatísticas da Fila."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from harness.domain.value_objects import RunStatus


class AgentRunRecord(BaseModel):
    """Registro de auditoria de uma execução do motor de cognição (FR-017, FR-020)."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    queue_item_id: UUID | None = Field(default=None)
    thread_id: str
    agent_name: str = Field(default="default_agent")
    llm_provider: str = Field(default="echo")
    llm_model: str = Field(default="echo-v1")
    prompt_version: str = Field(default="local-1.0.0")
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    guardrail_triggered: bool = Field(default=False)
    guardrail_reason: str | None = Field(default=None)
    status: RunStatus = Field(default=RunStatus.SUCCESS)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tokens(self) -> int:
        """Soma total de tokens consumidos no turno."""
        return self.prompt_tokens + self.completion_tokens


class QueueStats(BaseModel):
    """Resumo operacional de contagem de itens por estado para a Admin API (FR-018)."""

    model_config = ConfigDict(frozen=True)

    pending: int = Field(default=0, ge=0)
    processing: int = Field(default=0, ge=0)
    done: int = Field(default=0, ge=0)
    dead: int = Field(default=0, ge=0)
    quarantined_inbound: int = Field(default=0, ge=0)

