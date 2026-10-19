"""Testes Unitários da Camada de Domínio, Value Objects, Contratos e Configurações (T015).

Equivalente no C#/.NET: Testes xUnit com `[Fact]` e `[Theory]` validando invariantes de domínio,
imutabilidade de Value Objects e carregamento de `IOptions<HarnessSettings>`.
"""

from dataclasses import FrozenInstanceError
from uuid import UUID

from pydantic import ValidationError
import pytest

from harness.domain import (
    AgentRunRecord,
    CognitionEngineProtocol,
    MediaType,
    NormalizedTextMessage,
    PayloadNormalizationError,
    PhoneNumber,
    QueueItem,
    QueueStatus,
    RunStatus,
    Thread,
    ThreadId,
    ThreadMode,
)
from harness.settings import HarnessSettings


def test_phone_number_cleans_and_validates_digits() -> None:
    phone = PhoneNumber("+55 (11) 99999-8888")
    assert phone.value == "5511999998888"
    assert str(phone) == "5511999998888"


def test_phone_number_rejects_invalid_length() -> None:
    with pytest.raises(PayloadNormalizationError, match="entre 10 e 15 dígitos"):
        PhoneNumber("12345")


def test_phone_number_is_immutable() -> None:
    phone = PhoneNumber("5511999998888")
    with pytest.raises(FrozenInstanceError):
        phone.value = "5511000000000"  # type: ignore[misc]


def test_thread_id_derived_deterministically_from_phone() -> None:
    t1 = ThreadId.from_phone("+55 11 99999-8888")
    t2 = ThreadId("wa:5511999998888")
    assert t1 == t2
    assert t1.value == "wa:5511999998888"
    assert t1.phone_number == "5511999998888"


def test_normalized_text_message_enforces_strict_immutability_and_non_blank_text() -> None:
    msg = NormalizedTextMessage(
        provider_message_id="wamid.123",
        thread_id="wa:5511999998888",
        sender_phone="5511999998888",
        sender_name="Paulo",
        text_content="  Olá, quero saber sobre os planos  ",
        original_media_type=MediaType.TEXT,
    )
    assert msg.text_content == "Olá, quero saber sobre os planos"

    with pytest.raises(ValidationError):
        msg.text_content = "Tentativa de mutação"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        NormalizedTextMessage(
            provider_message_id="wamid.124",
            thread_id="wa:5511999998888",
            sender_phone="5511999998888",
            text_content="    ",
        )


def test_thread_bot_mode_and_queue_item_defaults() -> None:
    thread = Thread(thread_id="wa:5511999998888", phone_number="5511999998888")
    assert thread.is_bot_active is True

    human_thread = Thread(
        thread_id="wa:5511999998888",
        phone_number="5511999998888",
        mode=ThreadMode.HUMAN,
    )
    assert human_thread.is_bot_active is False

    item = QueueItem(thread_id="wa:5511999998888", concatenated_text="Oi\nTudo bem?")
    assert item.status == QueueStatus.PENDING
    assert item.phone_number == "5511999998888"


def test_agent_run_record_total_tokens() -> None:
    run = AgentRunRecord(
        thread_id="wa:5511999998888",
        prompt_tokens=120,
        completion_tokens=80,
        status=RunStatus.SUCCESS,
    )
    assert run.total_tokens == 200


def test_runtime_checkable_protocol_compliance() -> None:
    class DummyEngine:
        async def generate_reply(
            self,
            thread_id: ThreadId,
            user_text: str,
            queue_item_id: UUID | None = None,
        ) -> str:
            return f"Echo: {user_text}"

    assert isinstance(DummyEngine(), CognitionEngineProtocol)


def test_settings_loads_from_harness_yaml(test_settings: HarnessSettings) -> None:
    assert test_settings.app.name == "whatsapp-harness-mvp"
    assert test_settings.queue.debounce_seconds == 3.0
    assert test_settings.queue.max_retries == 3
    assert test_settings.rag.provider == "postgres"
    assert test_settings.prompts.default_prompt_name == "default_agent"

