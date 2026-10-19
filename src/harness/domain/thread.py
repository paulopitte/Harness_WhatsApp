"""Entidades de Domínio para Thread (Conversa), Mensagens Históricas e Fatos Semânticos (DDD).

Representa o estado persistente da conversa identificada pelo telefone (`thread_id`),
incluindo Handoff Humano (`mode`), orçamento de tokens e dupla memória (FR-014, FR-015).
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from harness.domain.value_objects import ThreadMode


class ThreadMessage(BaseModel):
    """Mensagem individual armazenada no histórico operacional de curto prazo da thread."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    thread_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    is_summarized: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SemanticFact(BaseModel):
    """Fato estável aprendido sobre o cliente (Memória Semântica — FR-014)."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    thread_id: str
    fact_key: str = Field(..., min_length=1, max_length=64)
    fact_value: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Thread(BaseModel):
    """Agregado principal da conversa no WhatsApp."""

    thread_id: str
    phone_number: str
    mode: ThreadMode = Field(default=ThreadMode.BOT)
    conversation_summary: str = Field(default="")
    daily_tokens_used: int = Field(default=0, ge=0)
    daily_tokens_reset_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rate_window_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rate_window_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_bot_active(self) -> bool:
        """Retorna True somente se o agente de IA estiver autorizado a responder nesta thread."""
        return self.mode == ThreadMode.BOT

