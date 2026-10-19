"""Camada de Domínio Puro (DDD) — Value Objects, Entidades, Exceções e Ports (typing.Protocol)."""

from harness.domain.events import AgentRunRecord, QueueStats
from harness.domain.exceptions import (
    GuardrailBlockedError,
    HarnessDomainError,
    OutboundDeliveryError,
    PayloadNormalizationError,
    RateLimitExceededError,
    SignatureVerificationError,
    TokenBudgetExceededError,
    UnsupportedMediaError,
)
from harness.domain.message import InboundMediaAttachment, InboundRawEvent, NormalizedTextMessage
from harness.domain.ports import (
    CognitionEngineProtocol,
    OutboundProviderProtocol,
    PromptProviderPort,
    PromptProviderProtocol,
    QueueConsumerProtocol,
    QueueEnqueuerProtocol,
    RetrieverPort,
    RetrieverProtocol,
)
from harness.domain.queue import QuarantineEntry, QueueItem
from harness.domain.thread import SemanticFact, Thread, ThreadMessage
from harness.domain.value_objects import (
    MediaType,
    PhoneNumber,
    QueueStatus,
    RunStatus,
    ThreadId,
    ThreadMode,
)

__all__ = [
    "AgentRunRecord",
    "CognitionEngineProtocol",
    "GuardrailBlockedError",
    "HarnessDomainError",
    "InboundMediaAttachment",
    "InboundRawEvent",
    "MediaType",
    "NormalizedTextMessage",
    "OutboundDeliveryError",
    "OutboundProviderProtocol",
    "PayloadNormalizationError",
    "PhoneNumber",
    "PromptProviderPort",
    "PromptProviderProtocol",
    "QuarantineEntry",
    "QueueConsumerProtocol",
    "QueueEnqueuerProtocol",
    "QueueItem",
    "QueueStats",
    "QueueStatus",
    "RateLimitExceededError",
    "RetrieverPort",
    "RetrieverProtocol",
    "RunStatus",
    "SemanticFact",
    "SignatureVerificationError",
    "Thread",
    "ThreadId",
    "ThreadMessage",
    "ThreadMode",
    "TokenBudgetExceededError",
    "UnsupportedMediaError",
]
