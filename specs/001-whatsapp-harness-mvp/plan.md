# Implementation Plan: WhatsApp Harness MVP

**Branch**: `001-whatsapp-harness-mvp` | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-whatsapp-harness-mvp/spec.md`

---

## Summary

Construir a **WhatsApp AI Harness MVP** em **Python 3.13** gerenciada com **`uv`**, seguindo rigorosamente **Clean Architecture, DDD, SOLID, KISS, YAGNI** e o padrão **Ports & Adapters (`typing.Protocol`)**. O sistema separa o processamento em três processos independentes (`webhook`, `worker`, `admin`), garantindo ACK HTTP `< 150ms` na borda (com Fast-Retry via `tenacity` e Quarentena `Edge DLQ`), fila transacional agnóstica inicialmente em **PostgreSQL 16 (`SKIP LOCKED`)** com debounce persistido via `scheduled_for` e idempotência por `provider_message_id`, motor de cognição em **LangGraph** com `ModelFactory` multi-LLM (Gemini, OpenAI, Ollama), RAG via `VectorStoreFactory` (`PGVector` no mesmo banco por padrão, extensível para `Qdrant`), Guardrails em 2 camadas, Pipeline de Middlewares (estilo MediatR), **PromptOps** com versionamento dinâmico no **Langfuse** + fallback YAML local, e ambiente 100% testável a custo zero (`EchoAgent` + `ConsoleOutboundProvider` + Simulador CLI).

---

## Technical Context

**Language/Version**: Python 3.13+ (gerenciado exclusivamente via `uv`)

**Primary Dependencies**:
- **Core & Web**: `fastapi`, `uvicorn[standard]`, `pydantic>=2.9`, `pydantic-settings`, `pyyaml`, `httpx`, `tenacity`
- **Database & Vector Store**: `psycopg[binary,pool]>=3.2`, `pgvector`, `langchain-postgres` (e `langchain-qdrant` / `qdrant-client` como extra opcional)
- **Cognition & AI**: `langchain>=1.0`, `langgraph>=1.0`, `langchain-core`, `langchain-google-genai`, `langchain-openai`, `langchain-ollama`
- **PromptOps & Observability**: `langfuse`, `structlog`, `opentelemetry-api`, `opentelemetry-sdk`

**Storage**: PostgreSQL 16+ com extensão `pgvector` (unificando fila transacional `SKIP LOCKED`, debounce `scheduled_for`, quarentena `Edge DLQ`, estado de threads, memória semântica e embeddings RAG).

**Testing**: `pytest`, `pytest-asyncio`, `ruff` (linter/formatter Clean Code), `mypy` (checagem estática estrita de tipos).

**Target Platform**: Containers Docker / Linux Server & Windows Local Dev Environment.

**Project Type**: Multi-process Backend Service & AI Agent Harness (`webhook`, `worker`, `admin` + `cli simulator`).

**Performance Goals**:
- Webhook HTTP ACK: `< 150ms` no P95.
- Throughput de fila no Postgres (`SKIP LOCKED`): suporte a dezenas de workers concorrentes com zero colisão de lock.

**Constraints**:
- Proibido invocar LLM ou grafo de cognição dentro da requisição HTTP do webhook.
- A fila só aceita texto pré-processado (`NormalizedTextMessage`).
- Tipagem estrita em todas as fronteiras (zero `dict[str, Any]` solto entre camadas).

**Scale/Scope**: MVP modular pronto para produção (21 Requisitos Funcionais distribuídos em 4 fases incrementais de entrega).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Princípio da Constitution (v1.1.0) | Status | Evidência no Plano e Design (`research.md`, `data-model.md`, `contracts/`) |
| :--- | :---: | :--- |
| **I. Arquitetura de Harness, DDD e Isolamento de Processos** | ✅ PASS | 3 entrypoints independentes (`run_webhook.py`, `run_worker.py`, `run_admin.py`); `domain/` puro sem dependências de I/O. |
| **II. Engenharia: SOLID, Clean Code, KISS e YAGNI** | ✅ PASS | Interfaces segregadas em `domain/ports.py` (`QueueEnqueuerProtocol` vs `QueueConsumerProtocol`); infraestrutura unificada em 1 container Postgres (`pgvector`) no MVP. |
| **III. Contrato Único de Fila e Fronteira Multimodal** | ✅ PASS | Fila só recebe `NormalizedTextMessage`; mídia é convertida em `edge/media/` antes do enqueue; `inbound_dedup` garante idempotência. |
| **IV. Identidade de Thread, Debounce e Dupla Memória** | ✅ PASS | `ThreadId` determinístico (`wa:<phone>`); debounce via `scheduled_for` e índice parcial `idx_queue_unique_pending_thread`; tabelas `thread_messages` + `semantic_facts`. |
| **V. Tipagem Forte, Validação e Controle de Dependências** | ✅ PASS | Modelos Pydantic v2 (`frozen=True` / `strict=True`) e `@dataclass(frozen=True)`; pacotes adicionais documentados e homologados na tabela abaixo. |
| **VI. Ciclo de Vida da Fila, Outbound e Retry (DLQ)** | ✅ PASS | Estados `pending -> processing -> done \| dead` no Postgres; `quarantine_inbound` para Edge DLQ. |
| **VII. Cobertura de Testes e Desenvolvimento Incremental** | ✅ PASS | Fases 1 e 2 entregam e validam Borda + Fila + Worker com `EchoAgent` e `ConsoleOutboundProvider` antes de acoplar LLM. |
| **VIII. Observabilidade, Configuração e Segredos** | ✅ PASS | Hierarquia `configs/harness.yaml` + `.env` via `pydantic-settings`; `Langfuse` + `structlog` + `OpenTelemetry` + tabela `agent_runs`. |

### Homologação de Dependências Adicionais (Conforme Princípio V da Constitution)

| Pacote | Camada | Justificativa Técnica |
| :--- | :--- | :--- |
| `tenacity` | `edge/resilience.py`, `outbound/retry.py` | Implementação padrão de mercado em Python (equivalente ao *Polly* do .NET) para Fast-Retry na borda e backoff exponencial no outbound. |
| `pgvector` & `langchain-postgres` | `cognition/retrievers/` | Permite usar o mesmo PostgreSQL 16 da fila como Vector Store RAG, evitando subir um segundo banco no MVP (KISS). |
| `langchain-qdrant` & `qdrant-client` | `cognition/retrievers/` | Adaptador plugável na `VectorStoreFactory` para suportar migração transparente para Qdrant via `harness.yaml`. |
| `langfuse` | `cognition/prompts/`, `ops/telemetry.py` | Atende aos requisitos FR-017 (Tracing de LLM) e FR-021 (Prompt Management com versionamento dinâmico e labels). |
| `structlog` & `opentelemetry-sdk` | `ops/telemetry.py` | Logging estruturado JSON com `correlation_id`/`thread_id` (equivalente ao *Serilog* do .NET) e métricas agnósticas. |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-whatsapp-harness-mvp/
├── spec.md                      # Especificação de requisitos (FR-001 a FR-021)
├── plan.md                      # Este plano técnico de implementação
├── research.md                  # Decisões arquiteturais (Phase 0)
├── data-model.md                # Entidades, estados e DDL SQL do Postgres 16 + pgvector (Phase 1)
├── quickstart.md                # Guia de execução e validação ponta a ponta (Phase 1)
├── contracts/
│   └── ports_and_apis.md        # Protocols Python (Interfaces) e contratos HTTP REST (Phase 1)
└── checklists/
    └── requirements.md          # Checklist de validação da especificação
```

### Source Code (repository root)

```text
d:\CURSOS\PYTHON\Harness_WhatsApp\
├── pyproject.toml               # Gerenciado via uv (Python 3.13+, dependências e configs do ruff/mypy/pytest)
├── docker-compose.yml           # Container único: pgvector/pgvector:pg16
├── .env.example                 # Template de variáveis sensíveis (DB, Meta, Gemini/OpenAI, Langfuse)
├── README.md                    # Documentação executiva e arquitetural do projeto (Case de Portfólio)
├── configs/
│   ├── harness.yaml             # Configuração operacional tipada (debounce, retries, llm, rag, guardrails)
│   └── prompts/
│       └── default_agent.yaml   # Fallback local versionado para o PromptProviderPort (FR-021)
├── migrations/
│   └── 001_initial_schema.sql   # DDL idempotente (threads, inbound_dedup, quarantine_inbound, queue_items, etc.)
│
├── src/harness/
│   ├── __init__.py
│   ├── settings.py              # Carregamento hierárquico (harness.yaml + .env) via pydantic-settings
│   ├── app.py                   # Composition Root (Injeção de Dependências conectando Ports e Adapters)
│   │
│   ├── domain/                  # CAMADA DE DOMÍNIO (Zero dependências externas)
│   │   ├── __init__.py
│   │   ├── exceptions.py        # HarnessDomainError, RateLimitExceededError, GuardrailBlockedError, etc.
│   │   ├── value_objects.py     # PhoneNumber, ThreadId, Enums (QueueStatus, ThreadMode, MediaType)
│   │   ├── message.py           # InboundWebhookPayload, NormalizedTextMessage
│   │   ├── thread.py            # Entidade Thread e SemanticFact
│   │   ├── queue.py             # Entidade QueueItem e QuarantineEntry
│   │   ├── events.py            # Eventos de domínio e telemetria (AgentRunRecord)
│   │   └── ports.py             # typing.Protocol: QueueEnqueuer, QueueConsumer, Outbound, Retriever, Prompt, Cognition
│   │
│   ├── edge/                    # CAMADA DE BORDA (Inbound ACL - FastAPI)
│   │   ├── __init__.py
│   │   ├── webhook.py           # Rotas GET /webhook e POST /webhook (ACK < 150ms)
│   │   ├── verify.py            # Validação HMAC X-Hub-Signature-256
│   │   ├── rate_limit.py        # Proteção anti-loop bot-to-bot por telefone
│   │   ├── normalize.py         # Sanitização de PII (Fast Guardrail) e criação de NormalizedTextMessage
│   │   ├── resilience.py        # Fast-Retry com tenacity e gravação na quarantine_inbound (Edge DLQ)
│   │   └── media/
│   │       ├── __init__.py
│   │       ├── router.py        # Roteador de mídia (texto | áudio | imagem | recusado)
│   │       ├── transcribe.py    # Adaptador de transcrição de áudio para texto
│   │       └── vision.py        # Adaptador de descrição de imagem para texto
│   │
│   ├── ingress/                 # ADAPTADORES DE FILA (Infraestrutura de Ingestão)
│   │   ├── __init__.py
│   │   ├── database.py          # Gerenciador do AsyncConnectionPool (psycopg v3)
│   │   └── postgres_queue.py    # Implementação de QueueEnqueuerProtocol e QueueConsumerProtocol (SKIP LOCKED + Debounce)
│   │
│   ├── persistence/             # REPOSITÓRIOS OPERACIONAIS
│   │   ├── __init__.py
│   │   ├── threads_repo.py      # Persistência de threads, histórico, modo (bot/human) e fatos semânticos
│   │   └── runs_repo.py         # Persistência de auditoria (agent_runs e quarantine_inbound)
│   │
│   ├── workers/                 # PROCESSAMENTO ASSÍNCRONO
│   │   ├── __init__.py
│   │   ├── pipeline.py          # Use Case: Claim -> Checa Handoff -> Cognição -> Outbound -> Done / Retry / Dead
│   │   └── runner.py            # Loop assíncrono de workers concorrentes com graceful shutdown
│   │
│   ├── cognition/               # INTELIGÊNCIA ARTIFICIAL (Bounded Context LangGraph)
│   │   ├── __init__.py
│   │   ├── echo_engine.py       # Implementação EchoAgent (CognitionEngineProtocol) para testes a custo zero
│   │   ├── factory.py           # ModelFactory agnóstica (Gemini, OpenAI, Ollama)
│   │   ├── guardrails.py        # Nós de Input Guardrail (Prompt Injection/Escopo) e Output Guardrail
│   │   ├── middlewares.py       # Pipeline Behaviors (Latência, Token Budget, Auditoria e Sumarização)
│   │   ├── graph.py             # StateGraph LangGraph compilado implementando CognitionEngineProtocol
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   └── manager.py       # PromptProviderPort (Langfuse Prompt Management com cache TTL + fallback YAML)
│   │   └── retrievers/
│   │       ├── __init__.py
│   │       └── factory.py       # VectorStoreFactory implementando RetrieverPort (PGVector, Qdrant, InMemory)
│   │
│   ├── outbound/                # CAMADA OUTBOUND (Outbound ACL)
│   │   ├── __init__.py
│   │   ├── sender.py            # Orquestrador de envio com retry
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── console.py       # ConsoleOutboundProvider (imprime no terminal para simulação local)
│   │       └── meta.py          # MetaOutboundProvider (envio real HTTP via httpx)
│   │
│   └── ops/                     # OPERAÇÃO, TELEMETRIA E ADMIN
│       ├── __init__.py
│       ├── telemetry.py         # Configuração do structlog, OpenTelemetry e Langfuse CallbackHandler
│       ├── security.py          # Validação de API Key administrativa
│       └── admin_api.py         # FastAPI Admin: stats da fila, reprocess-dead (DLQ) e toggle de Handoff humano
│
├── scripts/
│   ├── init_db.py               # Executa migrations/001_initial_schema.sql
│   ├── run_webhook.py           # Inicia processo da Borda (porta 8000)
│   ├── run_worker.py            # Inicia processo do Worker
│   ├── run_admin.py             # Inicia processo da Admin API (porta 8001)
│   ├── send_fake_msg.py         # Simulador CLI de webhooks (suporta texto, rajada/burst, duplicata e mídia)
│   └── seed_knowledge.py        # Indexa documentos de FAQ/Políticas no Vector Store configurado
│
└── tests/
    ├── conftest.py              # Fixtures globais (fakes em memória e conexão de teste)
    ├── unit/
    │   ├── test_domain_models.py
    │   ├── test_edge_normalize_and_verify.py
    │   ├── test_guardrails_and_middlewares.py
    │   └── test_prompt_fallback.py
    └── integration/
        ├── test_postgres_debounce_and_claim.py
        ├── test_worker_pipeline_retry_dlq.py
        └── test_webhook_and_admin_api.py
```

**Structure Decision**: Adotado o padrão de **Pacote Único Modular (`src/harness/`) com Múltiplos Entrypoints (`scripts/`)**. Essa escolha permite compartilhar o mesmo núcleo de domínio (`domain/`) e configurações (`settings.py`) com tipagem estrita, enquanto executa `webhook`, `worker` e `admin` em processos isolados.

---

## Fases de Implementação (Roadmap para `/speckit-tasks`)

1. **Fase 1 — Fundação, Configuração e Domínio Puro (DDD & SOLID)**:
   - Setup do `pyproject.toml` (`uv`), `docker-compose.yml` (`pgvector:pg16`), `configs/harness.yaml`, `migrations/001_initial_schema.sql`, `settings.py` e toda a camada `src/harness/domain/` (Value Objects, Entidades, Exceções e `ports.py`) + testes unitários de domínio.
2. **Fase 2 — O Esqueleto da Harness Ponta a Ponta (User Story 1 - P1)**:
   - Borda HTTP (`edge/`), Fast-Retry + Quarentena (`quarantine_inbound`), Fila Postgres com Debounce e `SKIP LOCKED` (`ingress/`), Worker Pipeline com `EchoAgent` + `ConsoleOutboundProvider` e Simulador CLI (`scripts/send_fake_msg.py`) + testes de integração da fila.
3. **Fase 3 — Cognição LangGraph, Multi-LLM, Guardrails e Middlewares (User Story 2 - P2)**:
   - `ModelFactory` (Gemini/OpenAI/Ollama), Nós de Input/Output Guardrails, Pipeline de Middlewares (latência, token budget), Grafo LangGraph (`cognition/graph.py`) e `MetaOutboundProvider`.
4. **Fase 4 — Dupla Memória, RAG Agnóstico (`PGVector`/`Qdrant`) e Mídia na Borda (User Story 3 - P3)**:
   - Auto-sumarização de contexto, extração de `semantic_facts`, `VectorStoreFactory` (`RetrieverPort`), script `seed_knowledge.py` e conversão de áudio/imagem na borda (`edge/media/`).
5. **Fase 5 — Handoff Humano, PromptOps Langfuse e Admin API (User Story 4 - P4)**:
   - `PromptProviderPort` (Langfuse Prompt Management com cache TTL + fallback YAML local), traces no Langfuse, logs estruturados `structlog`/OpenTelemetry, toggle de Handoff (`bot | human`) e `admin_api.py` (reprocessamento de DLQ).

---

## Complexity Tracking

> **Nenhuma violação à Constitution v1.1.0 foi introduzida.** Todas as abstrações (`Protocol` e Factories) atendem diretamente aos requisitos explícitos de intercambiabilidade (Fila, LLM, Vector Store e PromptOps) mantendo o runtime local unificado em um único container PostgreSQL (`pgvector`).

