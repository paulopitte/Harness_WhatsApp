"""Testes de Integração de Ingestão de Sites e Deep Research (Spec 002 — T060)."""

import pytest

from harness.cognition.deep_research import DeepResearchEngine
from harness.cognition.factory import DeterministicStubChatModelAdapter
from harness.cognition.graph import LangGraphCognitionEngine
from harness.cognition.retrievers.factory import InMemoryRetrieverAdapter
from harness.cognition.retrievers.web_search import DeterministicStubWebSearchAdapter
from harness.domain.ports import WebSearchResult
from harness.domain.value_objects import ThreadId
from harness.ingress.web_crawler import DeterministicStubWebsiteCrawlerAdapter
from harness.settings import DeepResearchConfig


@pytest.mark.asyncio
async def test_crawler_extracts_and_seeds_into_retriever() -> None:
    crawler = DeterministicStubWebsiteCrawlerAdapter()
    pages = await crawler.crawl_site("https://mawwal.com.br", max_pages=5)

    assert len(pages) == 1
    assert "Malek" in pages[0].title
    assert "R$ 489,00" in pages[0].content

    retriever = InMemoryRetrieverAdapter()
    chunks = [f"[{p.title}]\n{p.content}" for p in pages]
    count = await retriever.seed_documents(chunks)
    assert count == 1

    found = await retriever.retrieve_context("valor do perfume Malek", top_k=1)
    assert len(found) == 1
    assert "R$ 489,00" in found[0]


@pytest.mark.asyncio
async def test_langgraph_with_deep_research_disabled_uses_only_retriever() -> None:
    model = DeterministicStubChatModelAdapter(provider_name="stub", model_name="stub")
    retriever = InMemoryRetrieverAdapter([
        "Catálogo Mawwal: Perfume Malek Eau de Parfum 100ml custa R$ 489,00 com notas de oud real."
    ])

    engine = LangGraphCognitionEngine(
        model_adapter=model,
        retriever=retriever,
        deep_research_engine=None,  # deep_research.enabled = False
    )

    reply = await engine.generate_reply(
        thread_id=ThreadId("whatsapp:5511999998888"),
        user_text="Qual o preço do perfume Malek?",
    )

    assert reply != ""
    assert "Catálogo Mawwal" in reply
    assert "Fontes consultadas:" not in reply


@pytest.mark.asyncio
async def test_langgraph_with_deep_research_active_injects_web_facts() -> None:
    model = DeterministicStubChatModelAdapter(provider_name="stub", model_name="stub")
    search_stub = DeterministicStubWebSearchAdapter([
        WebSearchResult(
            title="História da Perfumaria Árabe",
            snippet="A perfumaria em Dubai valoriza ingredientes intensos como oud e almíscar.",
            link="https://mawwal.com.br/historia",
            source_name="Portal Mawwal",
        )
    ])
    cfg = DeepResearchConfig(enabled=True, include_sources=True)
    deep_engine = DeepResearchEngine(model, search_stub, config=cfg)

    engine = LangGraphCognitionEngine(
        model_adapter=model,
        deep_research_engine=deep_engine,
    )

    reply = await engine.generate_reply(
        thread_id=ThreadId("whatsapp:5511999998888"),
        user_text="Me fale sobre a história dos perfumes de Dubai",
    )

    assert reply != ""
    assert "stub" in reply
