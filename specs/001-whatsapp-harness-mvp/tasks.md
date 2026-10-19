---
description: "Lista de tarefas executáveis e ordenadas por dependência para o WhatsApp Harness MVP"
---

# Tasks: WhatsApp Harness MVP

**Input**: Design documents from `/specs/001-whatsapp-harness-mvp/` (`plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/ports_and_apis.md`, `quickstart.md`)

**Prerequisites**: Python 3.13+, `uv`, Docker Compose (PostgreSQL 16 + `pgvector`)

**Tests**: Cobertura obrigatória de testes unitários e de integração conforme Princípio VII da [Constitution v1.1.0](../../.specify/memory/constitution.md).

**Organization**: As tarefas estão agrupadas por fase e por User Story (`US1` a `US4`) para permitir implementação incremental, validação independente e aprendizado passo a passo (com paralelos didáticos C#/.NET -> Python 3.13).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Tarefa paralelizável (arquivos independentes, sem bloqueio mútuo)
- **[Story]**: Rastreabilidade direta para a User Story (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Todas as tarefas incluem o caminho exato do arquivo a ser criado ou modificado.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialização do pacote Python 3.13 com `uv`, infraestrutura Docker unificada (`pgvector`) e arquivos de configuração base.

- [ ] T001 Criar estrutura completa de pacotes e arquivos `__init__.py` em `src/harness/` (`domain`, `edge`, `edge/media`, `ingress`, `persistence`, `workers`, `cognition`, `cognition/prompts`, `cognition/retrievers`, `outbound`, `outbound/providers`, `ops`), `scripts/` e `tests/` (`unit`, `integration`, `load`)
- [ ] T002 Criar arquivo `pyproject.toml` na raiz com configuração do `uv`, Python `>=3.13`, dependências homologadas no `plan.md` e configurações estritas do `pytest`, `ruff` e `mypy`
- [ ] T003 [P] Criar `docker-compose.yml` na raiz com o serviço `postgres` utilizando a imagem `pgvector/pgvector:pg16`, healthcheck e volume persistente
- [ ] T004 [P] Criar `.env.example` na raiz e `configs/harness.yaml` com todas as chaves operacionais tipadas (`debounce_seconds`, `max_retries`, `rate_limit`, `llm`, `rag`, `guardrails`, `prompts`, `outbound`)
- [ ] T005 [P] Criar o arquivo de prompt local versionado `configs/prompts/default_agent.yaml` para servir de fallback offline e ambiente de teste (FR-021)

---

## Phase 2: Foundational (Core Domain, Ports, Settings & Database Schema)

**Purpose**: Camada de Domínio pura (DDD), Contratos (`typing.Protocol`), Configurações hierárquicas (`pydantic-settings`) e Schema SQL do PostgreSQL.

**⚠️ CRITICAL**: Nenhuma User Story pode ser iniciada antes da conclusão desta fase fundacional.

- [ ] T006 [P] Implementar hierarquia de exceções de domínio (`HarnessDomainError`, `SignatureVerificationError`, `PayloadNormalizationError`, `RateLimitExceededError`, `UnsupportedMediaError`, `GuardrailBlockedError`, `TokenBudgetExceededError`, `OutboundDeliveryError`) em `src/harness/domain/exceptions.py`
- [ ] T007 [P] Implementar Value Objects imutáveis (`PhoneNumber`, `ThreadId`) e Enums (`QueueStatus`, `ThreadMode`, `MediaType`) em `src/harness/domain/value_objects.py`
- [ ] T008 [P] Implementar contratos de mensagem (`InboundWebhookPayload`, `NormalizedTextMessage` com `ConfigDict(frozen=True, strict=True)`) em `src/harness/domain/message.py`
- [ ] T009 [P] Implementar entidades de estado (`Thread`, `SemanticFact`) em `src/harness/domain/thread.py` e entidades de fila/quarentena (`QueueItem`, `QuarantineEntry`) em `src/harness/domain/queue.py`
- [ ] T010 [P] Implementar modelos de eventos operacionais e auditoria (`AgentRunRecord`, `QueueStats`) em `src/harness/domain/events.py`
- [ ] T011 Implementar todas as interfaces segregadas (`QueueEnqueuerProtocol`, `QueueConsumerProtocol`, `OutboundProviderProtocol`, `RetrieverPort`, `PromptProviderPort`, `CognitionEngineProtocol`) em `src/harness/domain/ports.py`
- [ ] T012 Implementar carregamento hierárquico de configurações (`configs/harness.yaml` + `.env`) com validação Pydantic em `src/harness/settings.py`
- [ ] T013 Criar script DDL idempotente `migrations/001_initial_schema.sql` com as extensões `pgcrypto` e `vector` e as 7 tabelas (`threads`, `inbound_dedup`, `quarantine_inbound`, `queue_items`, `thread_messages`, `semantic_facts`, `agent_runs`) e índices parciais
- [ ] T014 Implementar gerenciador de `AsyncConnectionPool` (`psycopg` v3) em `src/harness/ingress/database.py` e utilitário de migração inicial em `scripts/init_db.py`
- [ ] T015 Criar testes unitários validando Value Objects, imutabilidade de `NormalizedTextMessage` e carregamento do `settings.py` em `tests/unit/test_domain_models.py`

**Checkpoint**: Fundação pronta — Domínio puro validado, contratos definidos e banco de dados estruturado.

---

## Phase 3: User Story 1 - Core Ingestion, Quarentena, Fila Agnóstica e Eco Testável (Priority: P1) 🎯 MVP

**Goal**: Receber webhooks na borda com ACK `< 150ms`, isolar falhas na quarentena (`Edge DLQ`), aplicar idempotência e debounce persistido no PostgreSQL, processar via worker com lock atômico (`SKIP LOCKED`), `EchoAgent` e `ConsoleOutboundProvider`, validando tudo localmente via simulador CLI a custo zero.

**Independent Test**: Rodar `scripts/run_webhook.py` e `scripts/run_worker.py`, disparar rajada de 3 mensagens com `scripts/send_fake_msg.py --burst` e comprovar que as 3 recebem `HTTP 200 OK` imediato, são concatenadas em 1 único item na fila e respondidas no console após o debounce de 3s.

### Tests for User Story 1 ⚠️

- [ ] T016 [P] [US1] Criar testes unitários de verificação HMAC, sanitização de PII e normalização de payload em `tests/unit/test_edge_normalize_and_verify.py`
- [ ] T017 [P] [US1] Criar testes de integração para idempotência (`inbound_dedup`), debounce persistido (`scheduled_for`) e claim concorrente (`SKIP LOCKED`) em `tests/integration/test_postgres_debounce_and_claim.py`

### Implementation for User Story 1

- [ ] T018 [P] [US1] Implementar validação criptográfica `X-Hub-Signature-256` em `src/harness/edge/verify.py`
- [ ] T019 [P] [US1] Implementar sanitização rápida de PII (Fast Guardrail de borda) e parser de payload para `NormalizedTextMessage` em `src/harness/edge/normalize.py`
- [ ] T020 [US1] Implementar Fast-Retry com `tenacity` (3 tentativas de 50ms/100ms/200ms) e persistência na tabela `quarantine_inbound` (Edge DLQ) em `src/harness/edge/resilience.py`
- [ ] T021 [US1] Implementar `PostgresQueueAdapter` cumprindo `QueueEnqueuerProtocol` (idempotência + upsert de debounce via índice parcial `idx_queue_unique_pending_thread`) e `QueueConsumerProtocol` (`FOR UPDATE SKIP LOCKED`, `mark_done`, `mark_failed_or_dead`) em `src/harness/ingress/postgres_queue.py`
- [ ] T022 [P] [US1] Implementar `EchoCognitionEngine` (cumprindo `CognitionEngineProtocol`) em `src/harness/cognition/echo_engine.py`
- [ ] T023 [P] [US1] Implementar `ConsoleOutboundProvider` (cumprindo `OutboundProviderProtocol`) em `src/harness/outbound/providers/console.py` e despachante `OutboundSender` em `src/harness/outbound/sender.py`
- [ ] T024 [US1] Implementar `ProcessQueueItemPipeline` (orquestrando claim -> cognição -> outbound -> confirmação `done` ou retry/DLQ `dead`) em `src/harness/workers/pipeline.py` e loop de polling concorrente em `src/harness/workers/runner.py`
- [ ] T025 [US1] Implementar endpoints `GET /webhook` e `POST /webhook` (ACK `< 150ms`) em `src/harness/edge/webhook.py`
- [ ] T026 [US1] Implementar Composition Root (wiring de dependências) em `src/harness/app.py` e scripts de inicialização `scripts/run_webhook.py` e `scripts/run_worker.py`
- [ ] T027 [US1] Implementar simulador CLI de webhooks `scripts/send_fake_msg.py` (com suporte a `--text`, `--burst`, `--duplicate` e `--corrupt`)

**Checkpoint**: User Story 1 (MVP Base da Harness) 100% funcional e testável ponta a ponta sem gastar 1 centavo com LLM ou Meta.

---

## Phase 4: User Story 2 - Cognição com LangGraph, LLM Agnóstica, Guardrails, Middlewares e Outbound Real (Priority: P2)

**Goal**: Conectar o grafo de inteligência em LangGraph com troca transparente de LLM (`ModelFactory`: Gemini, OpenAI, Ollama), nós de Input/Output Guardrails, Pipeline de Middlewares (latência e orçamento de tokens), proteção anti-loop na borda e provedor Outbound real da Meta.

**Independent Test**: Alternar `llm.provider` em `configs/harness.yaml` entre `gemini`, `openai` e `ollama`, disparar tanto perguntas legítimas quanto tentativas de *Prompt Injection* via simulador, e validar o bloqueio nos Guardrails e a contabilização no Middleware.

### Tests for User Story 2 ⚠️

- [ ] T028 [P] [US2] Criar testes unitários para `ModelFactory`, bloqueio de Prompt Injection nos Guardrails e enforcement de `TokenBudgetMiddleware` em `tests/unit/test_guardrails_and_middlewares.py`
- [ ] T029 [P] [US2] Criar testes de integração do pipeline do worker cobrindo retries exponenciais e transição para Business DLQ (`status = 'dead'`) em `tests/integration/test_worker_pipeline_retry_dlq.py`

### Implementation for User Story 2

- [ ] T030 [P] [US2] Implementar trava anti-loop bot-to-bot e rate limit por janela de tempo na tabela `threads` em `src/harness/edge/rate_limit.py`
- [ ] T031 [P] [US2] Implementar `ModelFactory` agnóstica instanciando modelos `gemini`, `openai` ou `ollama` a partir da configuração em `src/harness/cognition/factory.py`
- [ ] T032 [P] [US2] Implementar nós `input_guardrail_node` (detecção de Prompt Injection e fuga de escopo) e `output_guardrail_node` (prevenção de vazamento de prompt interno) em `src/harness/cognition/guardrails.py`
- [ ] T033 [US2] Implementar pipeline de Middlewares (`LatencyTrackingMiddleware`, `TokenBudgetMiddleware`, `AuditRunMiddleware`) estilo MediatR Pipeline Behavior em `src/harness/cognition/middlewares.py`
- [ ] T034 [US2] Implementar `LangGraphCognitionEngine` compilando o `StateGraph` completo e cumprindo `CognitionEngineProtocol` em `src/harness/cognition/graph.py`
- [ ] T035 [P] [US2] Implementar `MetaOutboundProvider` assíncrono com `httpx` e política de retry em `src/harness/outbound/providers/meta.py`

**Checkpoint**: User Stories 1 e 2 completas — Harness operando com LangGraph, Guardrails ativos, Middlewares e múltiplos provedores de LLM.

---

## Phase 5: User Story 3 - Dupla Memória, RAG Corporativo Agnóstico (`PGVector`/`Qdrant`) e Mídia na Borda (Priority: P3)

**Goal**: Dotar o agente de memória operacional com auto-sumarização, memória semântica de fatos do cliente, busca vetorial RAG agnóstica (`PGVector` no mesmo Postgres por padrão e `Qdrant` plugável) e conversão de áudio/imagem em texto na borda antes da fila.

**Independent Test**: Executar `scripts/seed_knowledge.py`, enviar uma pergunta sobre política da empresa e fatos pessoais (inclusive simulando payload de áudio/imagem) e verificar a transcrição na borda, a resposta embasada no RAG e o registro em `semantic_facts`.

### Tests for User Story 3 ⚠️

- [ ] T036 [P] [US3] Criar testes unitários e de integração para auto-sumarização de histórico, persistência de `semantic_facts`, `VectorStoreFactory` e roteador de mídia na borda em `tests/integration/test_memory_rag_and_media.py`

### Implementation for User Story 3

- [ ] T037 [P] [US3] Implementar `ThreadsRepository` (leitura/escrita de histórico `thread_messages`, atualização de `conversation_summary` e upsert de `semantic_facts`) em `src/harness/persistence/threads_repo.py`
- [ ] T038 [US3] Integrar auto-sumarização de janela de contexto e extração/injeção de fatos semânticos no grafo em `src/harness/cognition/middlewares.py` e `src/harness/cognition/graph.py`
- [ ] T039 [P] [US3] Implementar `VectorStoreFactory` e adaptadores cumprindo `RetrieverPort` (`PGVectorRetrieverAdapter`, `QdrantRetrieverAdapter`, `InMemoryRetrieverAdapter`) em `src/harness/cognition/retrievers/factory.py`
- [ ] T040 [US3] Adicionar ferramenta (Tool) `search_company_knowledge` ao agente LangGraph em `src/harness/cognition/graph.py` e criar script de indexação `scripts/seed_knowledge.py`
- [ ] T041 [P] [US3] Implementar roteador de mídia na borda (`text | audio | image | unsupported`) e conversores `AudioTranscriber` e `ImageVisionDescriber` em `src/harness/edge/media/router.py`, `src/harness/edge/media/transcribe.py` e `src/harness/edge/media/vision.py`

**Checkpoint**: User Stories 1, 2 e 3 completas — Agente com Dupla Memória, RAG unificado no Postgres (`pgvector`) ou `Qdrant` e suporte multimodal na borda.

---

## Phase 6: User Story 4 - Handoff Humano, PromptOps Langfuse, Operação e Observabilidade (Priority: P4)

**Goal**: Implementar gerenciamento e versionamento dinâmico de prompts via Langfuse (`PromptProviderPort` com cache TTL e fallback YAML local), tracing completo de LLM no Langfuse, logs estruturados com `structlog`/OpenTelemetry, pausa do bot para atendimento humano (Handoff `mode = 'human'`) e API Administrativa para inspeção e reprocessamento da DLQ (`dead`).

**Independent Test**: Alterar a thread para `mode = 'human'` via `PATCH /admin/threads/{id}/mode` e verificar que novas mensagens não acionam a LLM; testar fallback do `PromptManager` e reprocessar itens `dead` via `POST /admin/queue/reprocess-dead`.

### Tests for User Story 4 ⚠️

- [ ] T042 [P] [US4] Criar testes unitários do `PromptManager` (cache TTL, busca por label/versão no Langfuse e fallback automático para `configs/prompts/default_agent.yaml`) em `tests/unit/test_prompt_fallback.py`
- [ ] T043 [P] [US4] Criar testes de integração para Handoff Humano (`bot` vs `human`) e endpoints da `admin_api` (stats e reprocessamento de DLQ) em `tests/integration/test_webhook_and_admin_api.py`

### Implementation for User Story 4

- [ ] T044 [P] [US4] Implementar `PromptManager` cumprindo `PromptProviderPort` (integração com Langfuse Prompt Management, cache em memória TTL e fallback para YAML local) em `src/harness/cognition/prompts/manager.py`
- [ ] T045 [P] [US4] Implementar configuração de logs estruturados (`structlog` com `correlation_id`/`thread_id`), métricas OpenTelemetry e `CallbackHandler` do Langfuse em `src/harness/ops/telemetry.py`
- [ ] T046 [P] [US4] Implementar `RunsRepository` para gravação e consulta de `agent_runs` e `quarantine_inbound` em `src/harness/persistence/runs_repo.py`
- [ ] T047 [US4] Atualizar `ProcessQueueItemPipeline` em `src/harness/workers/pipeline.py` para verificar `thread.mode`: quando `'human'` ou `'paused'`, apenas registrar a mensagem no histórico e concluir sem invocar a LLM (FR-015)
- [ ] T048 [US4] Implementar autenticação por API Key em `src/harness/ops/security.py`, endpoints administrativos (`GET /admin/queue/stats`, `POST /admin/queue/reprocess-dead`, `PATCH /admin/threads/{thread_id}/mode`, `GET /admin/threads/{thread_id}/facts`) em `src/harness/ops/admin_api.py` e entrypoint `scripts/run_admin.py`

**Checkpoint**: Todas as 4 User Stories concluídas e integradas com governança corporativa completa.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Teste de carga e concorrência de workers, validação estática completa (`ruff` + `mypy`) e execução do guia `quickstart.md`.

- [ ] T049 [P] Implementar teste de carga e concorrência (disparo de 50 mensagens concorrentes em múltiplas threads consumidas por 4 workers em paralelo) em `tests/load/test_burst_concurrency.py`
- [ ] T050 Executar verificação estrita de tipos (`uv run mypy src/`), linter/formatter Clean Code (`uv run ruff check src/ tests/`) e validar todos os cenários do `specs/001-whatsapp-harness-mvp/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1 (Setup)**: Sem dependências — início imediato.
2. **Phase 2 (Foundational)**: Depende da Phase 1 — **BLOQUEIA** todas as User Stories porque define o Domínio, as `Ports` (`typing.Protocol`) e as tabelas do PostgreSQL.
3. **Phase 3 (US1 - Core Harness & Eco)**: Depende da Phase 2 — Entrega o MVP funcional da Harness a custo zero.
4. **Phase 4 (US2 - LangGraph, Multi-LLM, Guardrails & Middlewares)**: Depende da Phase 3 — Substitui o `EchoAgent` pelo motor real de IA mantendo a mesma porta `CognitionEngineProtocol`.
5. **Phase 5 (US3 - Dupla Memória, RAG PGVector/Qdrant & Mídia)**: Depende da Phase 4 — Enriquece a borda com mídia e o grafo com memória e RAG.
6. **Phase 6 (US4 - Handoff, PromptOps Langfuse & Admin API)**: Pode iniciar após a Phase 3 (para Handoff/Admin) e Phase 4 (para PromptOps/Tracing).
7. **Phase 7 (Polish & Load Testing)**: Depende da conclusão das fases anteriores.

### Parallel Opportunities

- Na **Phase 2**, `T006`, `T007`, `T008`, `T009` e `T010` atuam em arquivos distintos dentro de `src/harness/domain/` e podem ser implementados em paralelo.
- Na **Phase 3 (US1)**, `T018` (`verify.py`), `T019` (`normalize.py`), `T022` (`echo_engine.py`) e `T023` (`console.py`) não possuem dependências entre si.
- Na **Phase 4 (US2)**, `T030` (`rate_limit.py`), `T031` (`factory.py`), `T032` (`guardrails.py`) e `T035` (`meta.py`) são totalmente independentes.

---

## Parallel Example: User Story 1 (Phase 3)

```bash
# Bloco paralelo 1 - Testes iniciais (TDD):
Task T016: "Criar testes unitários de verificação HMAC, sanitização de PII e normalização em tests/unit/test_edge_normalize_and_verify.py"
Task T017: "Criar testes de integração para idempotência, debounce e SKIP LOCKED em tests/integration/test_postgres_debounce_and_claim.py"

# Bloco paralelo 2 - Componentes isolados da Borda e Adaptadores Mock:
Task T018: "Implementar validação criptográfica X-Hub-Signature-256 em src/harness/edge/verify.py"
Task T019: "Implementar sanitização de PII e parser para NormalizedTextMessage em src/harness/edge/normalize.py"
Task T022: "Implementar EchoCognitionEngine em src/harness/cognition/echo_engine.py"
Task T023: "Implementar ConsoleOutboundProvider em src/harness/outbound/providers/console.py"
```

---

## Implementation Strategy (Didática C#/.NET -> Python 3.13)

1. **Passo 1 (Fundação & Tipagem)**: Começaremos pelas **Phases 1 e 2** (`T001` a `T015`), onde você verá na prática como `pyproject.toml` (`uv`), `@dataclass(frozen=True)`, `Pydantic v2` e `typing.Protocol` dão ao Python a mesma segurança de compilação e arquitetura limpa de uma Solution `.sln` em .NET 10.
2. **Passo 2 (Esqueleto da Harness sem gastar 1 centavo)**: Implementaremos a **Phase 3 (US1)** (`T016` a `T027`) e veremos o webhook, o debounce no Postgres e o worker funcionando no terminal com o simulador CLI.
3. **Passo 3 (IA Profissional e Governança)**: Avançaremos pelas **Phases 4, 5, 6 e 7**, plugando LangGraph, Guardrails, Middlewares, RAG (`PGVector`/`Qdrant`), PromptOps no Langfuse e Handoff Humano sem nunca quebrar o que já foi construído!

