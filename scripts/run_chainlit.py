"""Entrypoint da Interface Web Interativa com Chainlit (`scripts/run_chainlit.py` — Spec 003, T063).

Uso:
    uv run chainlit run scripts/run_chainlit.py --port 8002
"""

import chainlit as cl

from harness.app import HarnessContainer, build_container
from harness.domain.value_objects import ThreadId
from harness.settings import get_settings

_container: HarnessContainer | None = None


async def get_or_build_container() -> HarnessContainer:
    global _container
    if _container is None:
        cfg = get_settings()
        _container = await build_container(cfg)
    return _container


@cl.on_chat_start
async def on_chat_start() -> None:
    session_id = cl.user_session.get("id") or "guest"
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
    thread_id_str = cl.user_session.get("thread_id") or "web_guest"
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
