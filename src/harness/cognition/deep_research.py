"""Subgrafo e Motor de Deep Research com 4 Estágios (`cognition/deep_research.py` — Spec 002, T055).

Inspirado no tutorial do LangGraph:
1. Planner / Query Generator: Decompõe a dúvida em buscas cirúrgicas.
2. Researcher: Executa busca aberta via `WebSearchPort` (DuckDuckGo).
3. Analyst: Avalia relevância, filtra ruídos e consolida fatos.
4. Synthesizer: Redige resumo executivo formatado para WhatsApp com citação de fontes.
"""


import re

from harness.cognition.factory import ChatModelAdapterProtocol
from harness.domain.ports import WebSearchPort, WebSearchResult
from harness.settings import DeepResearchConfig


class DeepResearchEngine:
    """Motor coordenador do fluxo de pesquisa profunda na Web."""

    def __init__(
        self,
        model: ChatModelAdapterProtocol,
        search_port: WebSearchPort,
        config: DeepResearchConfig | None = None,
    ) -> None:
        self._model = model
        self._search = search_port
        self._cfg = config or DeepResearchConfig()

    async def run_research(self, user_query: str) -> str:
        """Executa o pipeline completo de 4 estágios e retorna a resposta formatada."""
        if not self._cfg.enabled:
            return ""

        clean_query = user_query.strip()
        if not clean_query:
            return ""

        # 1. Planejamento / Geração de Queries
        search_queries = await self._plan_queries(clean_query)

        # 2. Execução da Busca Web (DuckDuckGo)
        collected_results: list[WebSearchResult] = []
        for q in search_queries[:2]:
            found = await self._search.search(q, max_results=self._cfg.max_results)
            collected_results.extend(found)

        if not collected_results:
            return ""

        # Deduplicação por link
        unique_results = {r.link: r for r in collected_results}
        results_list = list(unique_results.values())

        # 3. Análise de Relevância e Filtragem de Ruído
        analyzed_facts = await self._analyze_results(clean_query, results_list)

        # 4. Síntese Final com Resumo e Fontes para WhatsApp
        return await self._synthesize(clean_query, analyzed_facts, results_list)

    async def _plan_queries(self, user_query: str) -> list[str]:
        system_prompt = (
            "Você é um especialista em busca na web. "
            "Gere até 2 termos de pesquisa curtos e objetivos no DuckDuckGo para responder à dúvida. "
            "Retorne apenas os termos de busca, um por linha, sem numeração nem explicações."
        )
        res = await self._model.ainvoke_messages(
            system_prompt=system_prompt,
            user_message=user_query,
        )
        lines = [re.sub(r"^[\s\-*0-9.]+", "", line).strip() for line in res.content.splitlines() if line.strip()]
        return lines if lines else [user_query]

    async def _analyze_results(self, user_query: str, results: list[WebSearchResult]) -> str:
        formatted_results = "\n\n".join(
            f"Fonte [{i+1}] ({r.title}):\n{r.snippet}\nLink: {r.link}"
            for i, r in enumerate(results)
        )
        system_prompt = (
            "Você é um analista de dados e inteligência. "
            "Analise os resultados de busca e extraia apenas os fatos confiáveis, dados, "
            "números e conceitos que respondem diretamente à pergunta do usuário. "
            "Descarte propagandas e trechos irrelevantes."
        )
        user_message = (
            f"Pergunta original: {user_query}\n\n"
            f"Resultados coletados:\n{formatted_results}"
        )
        res = await self._model.ainvoke_messages(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        return res.content.strip()

    async def _synthesize(
        self,
        user_query: str,
        analyzed_facts: str,
        results: list[WebSearchResult],
    ) -> str:
        system_prompt = (
            "Você é o assistente virtual corporativo no WhatsApp. "
            "Com base nos fatos analisados, redija uma resposta amigável, clara e concisa para o cliente. "
            "Use linguagem natural, parágrafos curtos e destaque pontos importantes com negrito."
        )
        user_message = (
            f"Dúvida do cliente: {user_query}\n\n"
            f"Fatos confirmados:\n{analyzed_facts}"
        )
        res = await self._model.ainvoke_messages(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        final_text = res.content.strip()

        if self._cfg.include_sources and results:
            sources_block = "\n\n🌐 *Fontes consultadas:*\n" + "\n".join(
                f"• {r.title} ({r.link})" for r in results[:3]
            )
            final_text += sources_block

        return final_text
