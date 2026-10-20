"""Testes Unitários do Subgrafo Deep Research (Spec 002 — T056)."""

import pytest

from harness.cognition.deep_research import DeepResearchEngine
from harness.cognition.factory import DeterministicStubChatModelAdapter
from harness.cognition.retrievers.web_search import DeterministicStubWebSearchAdapter
from harness.domain.ports import WebSearchResult
from harness.settings import DeepResearchConfig


@pytest.mark.asyncio
async def test_deep_research_disabled_returns_empty() -> None:
    model = DeterministicStubChatModelAdapter(provider_name="stub", model_name="stub")
    search = DeterministicStubWebSearchAdapter()
    cfg = DeepResearchConfig(enabled=False)

    engine = DeepResearchEngine(model, search, config=cfg)
    result = await engine.run_research("O que é nota de oud?")

    assert result == ""


@pytest.mark.asyncio
async def test_deep_research_pipeline_executes_all_stages_with_sources() -> None:
    model = DeterministicStubChatModelAdapter(provider_name="stub", model_name="stub")
    search_results = [
        WebSearchResult(
            title="Oud: A Madeira dos Deuses",
            snippet="O oud é uma das resinas mais caras do mundo, usada na perfumaria árabe.",
            link="https://mawwal.com.br/blog/oud",
            source_name="Blog Mawwal",
        )
    ]
    search = DeterministicStubWebSearchAdapter(predefined_results=search_results)
    cfg = DeepResearchConfig(enabled=True, include_sources=True)

    engine = DeepResearchEngine(model, search, config=cfg)
    result = await engine.run_research("O que é nota de oud?")

    assert result != ""
    assert "Fontes consultadas:" in result
    assert "https://mawwal.com.br/blog/oud" in result


@pytest.mark.asyncio
async def test_deep_research_without_sources() -> None:
    model = DeterministicStubChatModelAdapter(provider_name="stub", model_name="stub")
    search_results = [
        WebSearchResult(
            title="Perfumaria Árabe",
            snippet="Tradição milenar em Dubai.",
            link="https://exemplo.com/perfumes",
            source_name="Portal Perfumes",
        )
    ]
    search = DeterministicStubWebSearchAdapter(predefined_results=search_results)
    cfg = DeepResearchConfig(enabled=True, include_sources=False)

    engine = DeepResearchEngine(model, search, config=cfg)
    result = await engine.run_research("História dos perfumes")

    assert result != ""
    assert "Fontes consultadas:" not in result

