"""Testes do Entrypoint do Chainlit (Spec 003 — T065)."""

import pytest

from harness.app import build_container
from harness.domain.value_objects import ThreadId
from harness.settings import get_settings


def test_chainlit_thread_id_format() -> None:
    session_id = "session_abc_123"
    thread_id = ThreadId(f"web:{session_id}")

    assert str(thread_id) == "web:session_abc_123"
    assert thread_id.phone_number == "session_abc_123"


@pytest.mark.asyncio
async def test_container_used_by_chainlit_can_generate_reply() -> None:
    cfg = get_settings()
    container = await build_container(cfg, force_in_memory=True)

    thread_id = ThreadId("web:guest_user")
    reply = await container.cognition_engine.generate_reply(
        thread_id=thread_id,
        user_text="Olá, teste da interface web",
    )

    assert reply != ""
    assert isinstance(reply, str)
