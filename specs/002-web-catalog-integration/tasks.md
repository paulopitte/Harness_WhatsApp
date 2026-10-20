# Tasks: Ingestão de Sites Web & Deep Research Opcional (002-web-knowledge-and-deep-research)

> **SpecKit — Fase 3: Checklist de Tarefas Guiadas por Testes (TDD)**  
> *Continuidade sequencial a partir da Tarefa T050 do MVP base.*

---

## 📋 Lista de Tarefas (P1 a P3)

### Fase 1: Contratos e Configuração (Feature Flags)
- [x] **T051**: Definir `WebsiteCrawlerConfig` e `DeepResearchConfig` em `src/harness/settings.py` e atualizar `configs/harness.yaml` com as flags `website_crawler.enabled` e `deep_research.enabled`.
- [x] **T052**: Definir `WebSearchPort` e `WebsiteCrawlerPort` em `src/harness/domain/ports.py`.

### Fase 2: Adaptador de Pesquisa Web Aberta (DuckDuckGo Search) & Subgrafo Deep Research
- [x] **T053**: Implementar `DuckDuckGoSearchAdapter` em `src/harness/cognition/retrievers/web_search.py` com timeout rígido de 5s, sanitização de snippets e tratamento de erro de conexão.
- [x] **T054**: Criar os prompts especializados de Deep Research: `configs/prompts/deep_research_planner.yaml`, `configs/prompts/deep_research_analyst.yaml` e `configs/prompts/deep_research_synthesizer.yaml`.
- [x] **T055**: Implementar o subgrafo LangGraph de Deep Research (Query Gen -> DDG -> Analista -> Resumo + Fontes) em `src/harness/cognition/deep_research.py`.
- [x] **T056**: Criar testes unitários para o adaptador de busca e o subgrafo em `tests/unit/test_deep_research.py`.

### Fase 3: Rastreador Agnóstico de Sites (Website Crawler)
- [x] **T057**: Implementar `HttpWebsiteCrawlerAdapter` em `src/harness/ingress/web_crawler.py` utilizando `httpx` assíncrono + `BeautifulSoup4` para extrair dados semânticos de qualquer site corporativo.
- [x] **T058**: Criar o script CLI agnóstico `scripts/crawl_website.py` para permitir rastrear qualquer URL corporativa (ex.: `https://mawwal.com.br`) e salvar os chunks no PostgreSQL `knowledge_documents`.

### Fase 4: Integração com LangGraph & Governança de Flags
- [x] **T059**: Modificar `src/harness/cognition/graph.py` para acoplar o subgrafo de Deep Research **apenas** quando `deep_research.enabled: true`. Garantir que quando `false`, nenhuma requisição externa de pesquisa ocorra.
- [x] **T060**: Criar testes de integração em `tests/integration/test_web_knowledge_and_deep_research.py` validando o chaveamento das flags e a resposta da IA com o case Mawwal.
- [x] **T061**: Documentar o uso do `crawl_website.py` e das flags de Deep Research no `README.md`.
