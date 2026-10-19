"""Contratos de Mensagem de Entrada e Texto Normalizado (Princípio III da Constitution).

Equivalente no C#/.NET: `record NormalizedTextMessage` validado via `FluentValidation`.
Em Python 3.13 com Pydantic v2, `ConfigDict(frozen=True, strict=True)` garante que o contrato
que entra na fila seja 100% imutável e validado estritamente na criação.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.domain.value_objects import MediaType, PhoneNumber, ThreadId


class NormalizedTextMessage(BaseModel):
    """Contrato único aceito pela fila de processamento (`QueuePort`).

    Regra de Ouro da Harness: Áudio e imagem morrem na borda e entram aqui já como texto.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    provider_message_id: str = Field(..., min_length=1, max_length=128)
    thread_id: str = Field(..., min_length=13, max_length=64)
    sender_phone: str = Field(..., min_length=10, max_length=15)
    sender_name: str = Field(default="Cliente")
    text_content: str = Field(..., min_length=1)
    original_media_type: MediaType = Field(default=MediaType.TEXT)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("sender_phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return PhoneNumber(v).value

    @field_validator("thread_id")
    @classmethod
    def _validate_thread_id(cls, v: str) -> str:
        return ThreadId(v).value

    @field_validator("text_content")
    @classmethod
    def _validate_non_blank_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O conteúdo textual normalizado não pode estar em branco.")
        return cleaned


class InboundMediaAttachment(BaseModel):
    """Metadados de anexo de mídia recebido na borda antes da transcrição/visão."""

    model_config = ConfigDict(frozen=True)

    media_id: str = Field(..., min_length=1)
    mime_type: str = Field(default="application/octet-stream")
    caption: str | None = Field(default=None)
    raw_bytes_b64: str | None = Field(default=None)


class InboundRawEvent(BaseModel):
    """Evento intermediário extraído do JSON bruto do webhook antes de virar NormalizedTextMessage."""

    model_config = ConfigDict(frozen=True)

    provider_message_id: str = Field(..., min_length=1)
    sender_phone: str = Field(..., min_length=1)
    sender_name: str = Field(default="Cliente")
    media_type: MediaType = Field(default=MediaType.TEXT)
    text_body: str | None = Field(default=None)
    media_attachment: InboundMediaAttachment | None = Field(default=None)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

