"""Adaptadores de Pesquisa na Web Aberta (`cognition/retrievers/web_search.py` — Spec 002, T053).

Equivalente no C#/.NET: `DuckDuckGoSearchService : IWebSearchService`
que implementa `WebSearchPort` com timeout estrito, sanitização e tratamento de exceções assíncronas.
"""

import asyncio
from typing import Any

import structlog

from harness.domain.ports import WebSearchResult

logger = structlog.get_logger(component="web-search")


class DuckDuckGoSearchAdapter:
    """Adaptador oficial de busca aberta na web usando a biblioteca `ddgs` (DuckDuckGo)."""

    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "duckduckgo"

    def _sync_search(self, query: str, max_results: int) -> list[WebSearchResult]:
        ddgs_cls: Any
        try:
            from ddgs import DDGS
            ddgs_cls = DDGS
        except Exception:
            import duckduckgo_search
            ddgs_cls = duckduckgo_search.DDGS

        try:
            with ddgs_cls() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results: list[WebSearchResult] = []
            for item in raw_results:
                title = str(item.get("title", "")).strip()
                snippet = str(item.get("body", "")).strip()
                link = str(item.get("href", "")).strip()
                if title and link:
                    results.append(
                        WebSearchResult(
                            title=title,
                            snippet=snippet,
                            link=link,
                            source_name="DuckDuckGo",
                        )
                    )
            return results
        except Exception as exc:
            logger.warning("duckduckgo_search_failed", query=query, error=str(exc))
            return []

    async def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        """Executa a busca de forma assíncrona protegida por timeout estrito para o WhatsApp."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_search, clean_query, max_results),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "duckduckgo_search_timeout",
                query=clean_query,
                timeout=self._timeout_seconds,
            )
            return []


class DeterministicStubWebSearchAdapter:
    """Adaptador determinístico para testes unitários offline sem chamadas reais de rede."""

    def __init__(self, predefined_results: list[WebSearchResult] | None = None) -> None:
        self.predefined_results = predefined_results or [
            WebSearchResult(
                title="História do Oud na Perfumaria Oriental",
                snippet="O oud é uma resina nobre e rara extraída da árvore aquilária...",
                link="https://exemplo.com.br/artigo-oud",
                source_name="Enciclopédia de Fragrâncias",
            )
        ]
        self.last_query: str | None = None

    @property
    def provider_name(self) -> str:
        return "stub"

    async def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        self.last_query = query
        return self.predefined_results[:max_results]
