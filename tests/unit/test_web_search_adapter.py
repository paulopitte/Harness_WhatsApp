"""Testes Unitários do Adaptador de Busca Web (Spec 002 — T054)."""

import pytest

from harness.cognition.retrievers.web_search import (
    DeterministicStubWebSearchAdapter,
    DuckDuckGoSearchAdapter,
)
from harness.domain.ports import WebSearchPort, WebSearchResult


def test_web_search_adapter_protocol_compliance() -> None:
    stub = DeterministicStubWebSearchAdapter()
    real = DuckDuckGoSearchAdapter()

    assert isinstance(stub, WebSearchPort)
    assert isinstance(real, WebSearchPort)
    assert stub.provider_name == "stub"
    assert real.provider_name == "duckduckgo"


@pytest.mark.asyncio
async def test_stub_web_search_adapter_returns_predefined_results() -> None:
    expected = [
        WebSearchResult(
            title="Perfumes de Luxo de Dubai",
            snippet="Guia completo sobre perfumaria árabe e essências raras.",
            link="https://exemplo.com.br/perfumes-dubai",
            source_name="Guia de Fragrâncias",
        )
    ]
    adapter = DeterministicStubWebSearchAdapter(predefined_results=expected)

    results = await adapter.search("perfumes dubai", max_results=2)

    assert len(results) == 1
    assert results[0].title == "Perfumes de Luxo de Dubai"
    assert results[0].link == "https://exemplo.com.br/perfumes-dubai"
    assert adapter.last_query == "perfumes dubai"


@pytest.mark.asyncio
async def test_duckduckgo_adapter_handles_empty_query() -> None:
    adapter = DuckDuckGoSearchAdapter(timeout_seconds=2.0)
    results = await adapter.search("   ", max_results=3)
    assert results == []


@pytest.mark.asyncio
async def test_duckduckgo_adapter_handles_timeout_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DuckDuckGoSearchAdapter(timeout_seconds=0.01)

    def _slow_sync_search(query: str, max_results: int) -> list[WebSearchResult]:
        import time
        time.sleep(0.1)
        return []

    monkeypatch.setattr(adapter, "_sync_search", _slow_sync_search)

    results = await adapter.search("qualquer busca", max_results=1)
    assert results == []

