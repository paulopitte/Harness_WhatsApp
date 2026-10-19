"""Value Objects imutáveis e Enums do Domínio (DDD).

Equivalente no C#/.NET: `readonly record struct PhoneNumber` e `enum QueueStatus`.
No Python 3.13, `@dataclass(frozen=True, slots=True)` cria Value Objects imutáveis,
comparáveis por valor e com baixo consumo de memória (`slots=True`), sem depender de bibliotecas externas.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from harness.domain.exceptions import PayloadNormalizationError

_DIGITS_ONLY_RE = re.compile(r"\D+")


class QueueStatus(StrEnum):
    """Estados transacionais do item na fila de processamento (FR-009)."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    DEAD = "dead"


class ThreadMode(StrEnum):
    """Modo de operação da conversa no WhatsApp (FR-015 — Handoff Humano)."""

    BOT = "bot"
    HUMAN = "human"
    PAUSED = "paused"


class MediaType(StrEnum):
    """Tipos de mídia reconhecidos na fronteira da borda (FR-016)."""

    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    UNSUPPORTED = "unsupported"


class RunStatus(StrEnum):
    """Resultado de auditoria da execução de um turno do agente."""

    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """Value Object imutável representando um telefone validado no formato E.164 (somente dígitos)."""

    value: str

    def __init__(self, raw_phone: str) -> None:
        cleaned = _DIGITS_ONLY_RE.sub("", raw_phone or "")
        if not (10 <= len(cleaned) <= 15):
            raise PayloadNormalizationError(
                f"Número de telefone inválido: '{raw_phone}'. Deve conter entre 10 e 15 dígitos."
            )
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ThreadId:
    """Value Object imutável que identifica deterministicamente uma conversa de WhatsApp (Princípio IV)."""

    value: str

    def __init__(self, raw_value: str) -> None:
        cleaned = (raw_value or "").strip()
        if not cleaned:
            raise PayloadNormalizationError("O identificador da thread (ThreadId) não pode ser vazio.")
        if not cleaned.startswith("wa:"):
            phone = PhoneNumber(cleaned)
            cleaned = f"wa:{phone.value}"
        else:
            PhoneNumber(cleaned.removeprefix("wa:"))
        object.__setattr__(self, "value", cleaned)

    @classmethod
    def from_phone(cls, phone: PhoneNumber | str) -> "ThreadId":
        """Constrói um ThreadId determinístico a partir de um PhoneNumber ou string."""
        phone_vo = phone if isinstance(phone, PhoneNumber) else PhoneNumber(phone)
        return cls(f"wa:{phone_vo.value}")

    @property
    def phone_number(self) -> str:
        """Retorna apenas os dígitos do telefone associado à thread."""
        return self.value.removeprefix("wa:")

    def __str__(self) -> str:
        return self.value

