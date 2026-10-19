"""Entidades de Fila Transacional (`QueueItem`) e Quarentena de Borda (`QuarantineEntry`).

Modelam o ciclo de vida `pending -> processing -> done | dead` (Business DLQ) e o
isolamento de payloads inválidos na borda (Edge DLQ — FR-004, FR-006, FR-009).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from harness.domain.value_objects import QueueStatus


class QueueItem(BaseModel):
    """Item da fila de processamento com suporte a debounce (`scheduled_for`) e retries."""

    id: UUID = Field(default_factory=uuid4)
    thread_id: str
    concatenated_text: str = Field(..., min_length=1)
    provider_message_ids: list[str] = Field(default_factory=list)
    status: QueueStatus = Field(default=QueueStatus.PENDING)
    attempts: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=1)
    last_error: str | None = Field(default=None)
    locked_by: str | None = Field(default=None)
    scheduled_for: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claimed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def phone_number(self) -> str:
        """Extrai o número de telefone a partir do thread_id (`wa:<phone>`)."""
        return self.thread_id.removeprefix("wa:")


class QuarantineEntry(BaseModel):
    """Registro de Quarentena de Borda (Edge DLQ — FR-004) para payloads corrompidos ou inválidos."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    provider_message_id: str | None = Field(default=None)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    error_reason: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

