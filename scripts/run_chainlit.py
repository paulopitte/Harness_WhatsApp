"""Entrypoint da Interface Web Interativa com Chainlit (`scripts/run_chainlit.py` — Spec 003, T063).

Uso:
    uv run chainlit run scripts/run_chainlit.py --port 8002
"""

import asyncio
import os
import sys
from uuid import uuid4

# No Windows, o driver assíncrono do psycopg v3 requer SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Desativa o data layer interno do Chainlit antes que ele leia o .env
os.environ.pop("DATABASE_URL", None)

import chainlit as cl  # noqa: E402
import chainlit.data  # noqa: E402

from harness.app import HarnessContainer, build_container  # noqa: E402
from harness.domain.value_objects import ThreadId  # noqa: E402
from harness.settings import get_settings  # noqa: E402

chainlit.data._data_layer_initialized = True
chainlit.data._data_layer = None

_container: HarnessContainer | None = None


async def get_or_build_container() -> HarnessContainer:
    global _container
    if _container is None:
        cfg = get_settings()
        _container = await build_container(cfg)
    return _container


@cl.on_chat_start
async def on_chat_start() -> None:
    session_id = cl.user_session.get("id") or str(uuid4())
    thread_id = str(ThreadId(f"web:{session_id}"))
    cl.user_session.set("thread_id", thread_id)

    container = await get_or_build_container()
    agent_name = container.settings.prompts.default_prompt_name if hasattr(container, "settings") else "Assistente"

    await cl.Message(
        content=(
            f"👋 Olá! Eu sou o **{agent_name}** da WhatsApp AI Harness.\n\n"
            f"Estou conectado ao motor cognitivo (**LangGraph + Ollama/LLM**) com acesso à nossa "
            f"**base de conhecimento (RAG)** e à **memória semântica** contínua.\n\n"
            f"*Como posso te ajudar hoje?*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    thread_id_str = cl.user_session.get("thread_id") or "web:guest"
    thread_id = ThreadId(thread_id_str)
    container = await get_or_build_container()

    msg = cl.Message(content="")
    await msg.send()

    try:
        reply = await container.cognition_engine.generate_reply(
            thread_id=thread_id,
            user_text=message.content,
        )
        msg.content = reply
        await msg.update()
    except Exception as exc:
        msg.content = f"❌ Ocorreu um erro ao processar sua solicitação: {exc}"
        await msg.update()
