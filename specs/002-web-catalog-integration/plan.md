# Plano Arquitetural: Ingestão de Catálogo Web & Deep Research Opcional (002-web-catalog-integration)

> **SpecKit — Fase 2: Architecture & Technical Design**  
> *Paralelos didáticos com C# / .NET 10 para máxima clareza arquitetural.*

---

## 🏛️ 1. Mapeamento de Camadas & Paralelos com C# / .NET 10

| Componente Python (Harness) | Equivalente no C# / .NET 10 | Camada Arquitetural | Responsabilidade |
| :--- | :--- | :--- | :--- |
| `CatalogRetrieverPort` (`Protocol`) | `ICatalogRetriever` / `IVectorStore` | **Domain / Ports** | Contrato agnóstico de busca no catálogo corporativo. |
| `WebSearchPort` (`Protocol`) | `IWebSearchService` / `ISearchEngine` | **Domain / Ports** | Contrato agnóstico para pesquisa profunda na internet aberta. |
| `DuckDuckGoSearchAdapter` | `DuckDuckGoSearchService : IWebSearchService` | **Cognition / Adapters** | Implementação com `duckduckgo-search` sem necessidade de chave de API. |
| `HttpWebCrawlerAdapter` | `WebCrawlerService : ICatalogCrawler` | **Ingress / Crawler** | Varre páginas web do cliente via `httpx` + `BeautifulSoup4`. |
| `CatalogConfig` & `DeepResearchConfig` | `IOptions<CatalogOptions>`, `IOptions<DeepResearchOptions>` | **Infrastructure / Settings** | Modelos tipados com flags de ativação via Pydantic. |
| LangGraph `research_node` / Tool | `KernelFunction` (`SemanticKernel`) / `AITool` | **Cognition / LangGraph** | Ferramenta acionada sob demanda de acordo com as feature flags. |

---

## 📐 2. Contratos e Interfaces Formais (`domain/ports.py`)

### 2.1 Porta de Pesquisa Web Aberta (`WebSearchPort`)
```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class WebSearchPort(Protocol):
    """Porta agnóstica para pesquisa na Web (DuckDuckGo, Tavily, Google Search)."""

    @property
    def provider_name(self) -> str: ...

    async def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        """Executa busca assíncrona na Web e retorna lista de resultados {'title', 'snippet', 'link'}."""
        ...
```

### 2.2 Porta do Crawler de Catálogo (`WebCatalogCrawlerPort`)
```python
@runtime_checkable
class WebCatalogCrawlerPort(Protocol):
    """Porta para extração de dados e produtos de uma URL alvo de forma agnóstica."""

    async def crawl_catalog(self, base_url: str, max_pages: int = 50) -> list[dict[str, Any]]:
        """Extrai produtos/páginas retornando [{'title', 'content', 'url', 'metadata'}]."""
        ...
```

---

## 🛡️ 3. Regra de Negócio: Chaveamento de Feature Flags

No motor do LangGraph ([`src/harness/cognition/graph.py`](file:///d:/CURSOS/PYTHON/Harness_WhatsApp/src/harness/cognition/graph.py)):

1. **Se `catalog.enabled == true`:**
   * O RAG injeta o contexto do catálogo no System Prompt OU disponibiliza a Tool `search_catalog`.
2. **Se `deep_research.enabled == true`:**
   * A Tool `search_web` (DuckDuckGo) é registrada no modelo LLM. O modelo decide quando usá-la se a base interna for insuficiente.
3. **Se `deep_research.enabled == false`:**
   * A Tool `search_web` **NÃO é registrada** no grafo. Zero chamadas para fora do ecossistema local do cliente!

---

## 🧪 4. Estratégia de Testes (TDD & Mocking)

1. **Testes Unitários:**
   * `test_duckduckgo_adapter_respects_timeout_and_returns_clean_snippets`: valida parsing de resultados sem quebrar se a web oscilar.
   * `test_deep_research_disabled_flag_blocks_web_tool`: garante que com `deep_research.enabled: false` nenhuma conexão de rede externa ocorre.
2. **Testes de Integração:**
   * `test_web_crawler_extracts_product_cards`: valida extração em páginas HTML simuladas (Mock HTTP).
   * `test_catalog_indexed_chunks_retrieved_in_langgraph`: garante que o fluxo completo de consulta com o caso Mawwal responde corretamente.

