"""Testes Unitários e de Integração da Phase 5: Dupla Memória, RAG Agnóstico e Mídia na Borda (`T036`)."""

import pytest

from harness.cognition.factory import ModelFactory
from harness.cognition.graph import (
    LangGraphCognitionEngine,
    create_search_company_knowledge_tool,
)
from harness.cognition.middlewares import (
    AuditRunMiddleware,
    ConversationMemoryMiddleware,
    InMemoryAgentRunRepository,
    MiddlewarePipeline,
)
from harness.cognition.retrievers.factory import (
    DEFAULT_COMPANY_KNOWLEDGE,
    VectorStoreFactory,
)
from harness.domain.exceptions import UnsupportedMediaError
from harness.domain.message import InboundMediaAttachment, InboundRawEvent
from harness.domain.value_objects import MediaType, ThreadId
from harness.edge.media.router import EdgeMediaRouter
from harness.edge.normalize import build_normalized_text_message
from harness.persistence.threads_repo import InMemoryThreadsRepository
from harness.settings import EdgeMediaConfig, HarnessSettings, LlmConfig, RagConfig


@pytest.mark.asyncio
async def test_dual_memory_auto_summarization_and_semantic_facts() -> None:
    """Valida que:
    1. Fatos semânticos (`nome_cliente`, `empresa`, `plano_interesse`) são extraídos e persistidos.
    2. Quando `thread_messages` atinge `max_messages_before_summary`, as mensagens antigas são
       compactadas em `conversation_summary` (`is_summarized=True`) mantendo apenas as recentes ativas.
    3. Os fatos semânticos sobrevivem intactos após a compactação (Pilares 2 e 3 da Harness — FR-014).
    """
    settings = HarnessSettings(harness_env="test")
    threads_repo = InMemoryThreadsRepository()
    run_repo = InMemoryAgentRunRepository()
    model = ModelFactory.create(
        LlmConfig(provider="gemini", model="gemini-2.5-flash"),
        settings=settings,
    )

    # Configura auto-sumarização após 6 mensagens ativas (3 turnos User + Assistant), mantendo as 2 últimas
    memory_mw = ConversationMemoryMiddleware(
        threads_repo,
        max_messages_before_summary=6,
        keep_recent_after_summary=2,
    )
    engine = LangGraphCognitionEngine(
        model_adapter=model,
        middleware_pipeline=MiddlewarePipeline([AuditRunMiddleware(run_repo), memory_mw]),
    )

    thread_vo = ThreadId("wa:5511955554444")

    # Turno 1: Cliente se apresenta e informa empresa (gera 2 msgs ativas: user + assistant)
    await engine.generate_reply(
        thread_vo,
        "Olá! Meu nome é Carlos Mendes e trabalho na TechNova.",
    )
    facts_after_t1 = await threads_repo.get_semantic_facts(str(thread_vo))
    assert facts_after_t1.get("nome_cliente") == "Carlos Mendes"
    assert facts_after_t1.get("empresa") == "TechNova"
    active_after_t1 = await threads_repo.get_active_messages(str(thread_vo))
    assert len(active_after_t1) == 2

    # Turno 2: Cliente demonstra interesse em plano (gera 4 msgs ativas no total)
    await engine.generate_reply(
        thread_vo,
        "Tenho interesse no plano Growth para minha operação de suporte.",
    )
    facts_after_t2 = await threads_repo.get_semantic_facts(str(thread_vo))
    assert facts_after_t2.get("plano_interesse", "").lower() == "growth"
    active_after_t2 = await threads_repo.get_active_messages(str(thread_vo))
    assert len(active_after_t2) == 4

    # Turno 3: Atinge 6 mensagens ativas -> dispara compactação automática mantendo apenas as 2 últimas!
    await engine.generate_reply(
        thread_vo,
        "Qual é o prazo de ativação na Meta Cloud API?",
    )
    active_after_t3 = await threads_repo.get_active_messages(str(thread_vo))
    assert len(active_after_t3) == 2

    thread_state = await threads_repo.get_or_create_thread(str(thread_vo))
    assert "Tópicos abordados pelo cliente" in thread_state.conversation_summary
    assert "Carlos Mendes" in thread_state.conversation_summary

    # Memória Semântica continua intacta após a sumarização da janela operacional
    facts_after_t3 = await threads_repo.get_semantic_facts(str(thread_vo))
    assert facts_after_t3["nome_cliente"] == "Carlos Mendes"
    assert facts_after_t3["empresa"] == "TechNova"
    assert facts_after_t3["plano_interesse"].lower() == "growth"


@pytest.mark.asyncio
async def test_vector_store_factory_and_rag_tool_grounded_answers() -> None:
    """Valida a `VectorStoreFactory` (`in_memory` e `qdrant`) e a tool `search_company_knowledge` no grafo (FR-013)."""
    settings = HarnessSettings(harness_env="test")
    rag_cfg = RagConfig(provider="in_memory", collection_name="company_knowledge", top_k=2)
    retriever = VectorStoreFactory.create(rag_cfg, settings=settings, seed_defaults_if_in_memory=True)

    # 1. Testa invocação direta da Tool LangChain `search_company_knowledge`
    tool = create_search_company_knowledge_tool(retriever, top_k=2)
    tool_output = await tool.ainvoke({"query": "Qual a política de reembolso e cancelamento?"})
    assert "7 dias corridos" in str(tool_output)

    # 2. Testa o LangGraphCognitionEngine injetando o contexto RAG automaticamente
    model = ModelFactory.create(
        LlmConfig(provider="gemini", model="gemini-2.5-flash"),
        settings=settings,
    )
    engine = LangGraphCognitionEngine(
        model_adapter=model,
        retriever=retriever,
        rag_top_k=2,
    )
    reply = await engine.generate_reply(
        ThreadId("wa:5511944443333"),
        "Quais são os planos corporativos e preços mensais?",
    )
    assert "Base RAG:" in reply
    assert "Plano Starter" in reply or "R$ 299" in reply

    # 3. Valida troca agnóstica para `qdrant` via VectorStoreFactory
    qdrant_cfg = RagConfig(provider="qdrant", collection_name="company_knowledge", top_k=2)
    qdrant_retriever = VectorStoreFactory.create(qdrant_cfg, settings=settings)
    await qdrant_retriever.seed_documents(DEFAULT_COMPANY_KNOWLEDGE)  # type: ignore[attr-defined]
    qdrant_chunks = await qdrant_retriever.retrieve_context("horário de atendimento suporte humano")
    assert len(qdrant_chunks) >= 1
    assert "08h às 19h" in qdrant_chunks[0]


@pytest.mark.asyncio
async def test_edge_media_router_converts_audio_and_image_and_rejects_video() -> None:
    """Valida que áudio e imagem viram texto na borda antes da fila e que vídeo é recusado sem gastar LLM (FR-016)."""
    router = EdgeMediaRouter(EdgeMediaConfig(audio_enabled=True, image_enabled=True))

    # 1. Áudio na borda -> vira `[Áudio Transcrito]: ...` e entra em `NormalizedTextMessage`
    audio_event = InboundRawEvent(
        provider_message_id="wamid.audio.001",
        sender_phone="5511933332222",
        sender_name="Fernanda",
        media_type=MediaType.AUDIO,
        media_attachment=InboundMediaAttachment(
            media_id="media_audio_99",
            mime_type="audio/ogg; codecs=opus",
            caption="Quero saber se posso pedir reembolso em 7 dias",
        ),
    )
    resolved_audio_text = await router.resolve_to_text(audio_event)
    assert resolved_audio_text.startswith("[Áudio Transcrito]:")
    normalized_audio = build_normalized_text_message(audio_event, resolved_text=resolved_audio_text)
    assert normalized_audio.original_media_type == MediaType.AUDIO
    assert "reembolso em 7 dias" in normalized_audio.text_content

    # 2. Imagem na borda -> vira `[Imagem Descrita]: ...` e entra em `NormalizedTextMessage`
    image_event = InboundRawEvent(
        provider_message_id="wamid.img.002",
        sender_phone="5511933332222",
        sender_name="Fernanda",
        media_type=MediaType.IMAGE,
        media_attachment=InboundMediaAttachment(
            media_id="media_img_77",
            mime_type="image/jpeg",
            caption="Comprovante PIX no valor de R$ 299,00 referente ao Plano Starter",
        ),
    )
    resolved_img_text = await router.resolve_to_text(image_event)
    assert resolved_img_text.startswith("[Imagem Descrita]:")
    normalized_img = build_normalized_text_message(image_event, resolved_text=resolved_img_text)
    assert normalized_img.original_media_type == MediaType.IMAGE
    assert "Comprovante PIX" in normalized_img.text_content

    # 3. Vídeo (`MediaType.UNSUPPORTED`) -> lança `UnsupportedMediaError` com texto amigável de recusa
    video_event = InboundRawEvent(
        provider_message_id="wamid.vid.003",
        sender_phone="5511933332222",
        sender_name="Fernanda",
        media_type=MediaType.UNSUPPORTED,
    )
    with pytest.raises(UnsupportedMediaError) as exc_info:
        await router.resolve_to_text(video_event)
    assert "só consigo processar mensagens de texto, áudio ou imagem" in exc_info.value.reply_text

