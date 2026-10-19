# Phase 0: Architectural & Technical Research (`research.md`)

**Feature**: `001-whatsapp-harness-mvp`  
**Date**: 2026-10-19  
**Spec**: [spec.md](./spec.md)

Este documento consolida as decisões técnicas e arquiteturais (estilo ADR - *Architecture Decision Records*) tomadas para o **WhatsApp Harness MVP**, garantindo aderência total à [Constitution v1.1.0](../../.specify/memory/constitution.md) e resolvendo todas as escolhas de integração.

---

## 1. Fila Transacional e Debounce Persistido no PostgreSQL

- **Decision**: Implementar o `PostgresQueueAdapter` utilizando `SELECT ... FOR UPDATE SKIP LOCKED` para consumo concorrente pelos workers e uma coluna `scheduled_for (TIMESTAMPTZ)` combinada com `UNIQUE (thread_id) WHERE status = 'pending'` para realizar o **Debounce Persistido** diretamente no banco de dados.
- **Rationale**:
  - Fazer debounce em memória dentro do processo FastAPI (ex.: `asyncio.sleep(3)`) viola o princípio de statelessness da borda: se houver 2 réplicas do webhook ou se o processo reiniciar durante os 3 segundos, mensagens são perdidas ou processadas fora de ordem.
  - Com o debounce no PostgreSQL (`INSERT ... ON CONFLICT (thread_id) WHERE status = 'pending' DO UPDATE SET payload = ..., scheduled_for = NOW() + interval '3 seconds'`), o webhook responde `HTTP 200 OK` em `< 20ms`, e o worker só faz claim quando `scheduled_for <= NOW()`.
  - Mantemos a interface `QueueEnqueuerProtocol` e `QueueConsumerProtocol` (`typing.Protocol`) 100% agnóstica para futura migração para RabbitMQ, Redis Streams ou AWS SQS sem alterar a borda nem o pipeline do worker.
- **Alternatives considered**:
  - *Debounce em memória (`asyncio.Task` no FastAPI)*: Rejeitado por risco de perda de dados em restart e impossibilidade de escalar horizontalmente a borda.
  - *Redis + Celery logo no Dia 1*: Rejeitado por ferir KISS/YAGNI no MVP (exigiria mais containers e coordenação distribuída quando o Postgres 16 suporta facilmente milhares de jobs/segundo com `SKIP LOCKED`).

---

## 2. Resiliência na Borda: Fast-Retry (`tenacity`) + Quarentena (`Edge DLQ`)

- **Decision**: Utilizar a biblioteca `tenacity` na camada `edge/resilience.py` para envolver a escrita no banco com 3 tentativas ultrarrápidas (`50ms`, `100ms`, `200ms`) para falhas transitórias de conexão, e gravar payloads malformados ou falhas de transcrição de mídia na tabela `quarantine_inbound` (retornando `HTTP 200 OK` ao provedor).
- **Rationale**:
  - Equivalente direto às políticas `WaitAndRetry` do *Polly* no .NET.
  - Se o erro for de payload inválido ou mídia corrompida, devolver `HTTP 500` para a Meta causaria tempestade de retries por 24 horas. Isolar na `quarantine_inbound` (Edge DLQ) e responder `200 OK` protege a saúde da borda sem perder o evento bruto para auditoria.
  - Somente se o banco de dados estiver completamente indisponível após o Fast-Retry é que a borda retorna `HTTP 503 Service Unavailable`, delegando a retentativa de entrega para a infraestrutura da Meta.
- **Alternatives considered**:
  - *Spool em arquivo de disco local*: Complexidade extra desnecessária dado que a Meta já possui política de retry exponencial quando recebe HTTP 5xx.

---

## 3. Banco Vetorial Unificado (`PGVector`) com Fábrica Agnóstica (`VectorStoreFactory`)

- **Decision**: Adotar o PostgreSQL 16 com a extensão `pgvector` (`langchain-postgres`) como implementação padrão da porta `RetrieverPort` no MVP, encapsulado por uma `VectorStoreFactory` que também suporta `Qdrant` (`langchain-qdrant`) e `InMemoryVectorStore` via configuração (`configs/harness.yaml`).
- **Rationale**:
  - Reduz a infraestrutura local do MVP a **um único container Docker** (`pgvector/pgvector:pg16`), servindo simultaneamente a fila, o estado das threads, os fatos semânticos e a busca vetorial RAG.
  - Preserva o princípio Open/Closed (SOLID): o nó/tool do agente depende apenas de `RetrieverPort.retrieve(query: str) -> list[KnowledgeChunk]`. Mudar para Qdrant em produção exige apenas trocar `rag.provider: "qdrant"` no YAML.
- **Alternatives considered**:
  - *Subir container Qdrant obrigatório desde o passo 1*: Aumenta o consumo de RAM local sem necessidade imediata no MVP; mantido como adaptador plugável.

---

## 4. Cognição Multi-LLM (`ModelFactory`), Guardrails e Pipeline de Middlewares

- **Decision**:
  1. **`ModelFactory`**: Fábrica centralizada em `src/harness/cognition/factory.py` que instancia `BaseChatModel` do LangChain v1 (`gemini`, `openai`, `ollama`) a partir do `harness.yaml`.
  2. **Guardrails em 2 Camadas**:
     - *Camada 1 (Borda)*: Regex/Sanitização determinística de PII (CPF, cartões) e bloqueio de payloads gigantes sem gastar LLM.
     - *Camada 2 (Grafo LangGraph)*: Nós dedicados `input_guardrail_node` (classificação rápida de Prompt Injection e escopo) e `output_guardrail_node` (prevenção de vazamento de system prompt).
  3. **Pipeline de Middlewares (`cognition/middlewares.py`)**: Estrutura inspirada no `IPipelineBehavior` do MediatR (.NET), interceptando a execução do grafo para medir latência, contabilizar tokens consumidos, validar o orçamento diário da thread (`token_budget`) e acionar sumarização de contexto.
- **Rationale**:
  - Garante que ataques de Prompt Injection morram antes de invocar o agente principal com RAG, economizando tokens e protegendo o negócio.
  - Oferece aos desenvolvedores vindos de C#/.NET uma estrutura limpa e testável para preocupações transversais (*cross-cutting concerns*).
- **Alternatives considered**:
  - *Misturar lógica de log, contagem de tokens e guardrails dentro do prompt do agente único*: Rejeitado por violar Single Responsibility Principle (SRP) e dificultar testes unitários.

---

## 5. PromptOps: Versionamento Dinâmico no Langfuse com Fallback Local

- **Decision**: Implementar a porta `PromptProviderPort` com dois adaptadores em cadeia (*Chain of Responsibility / Fallback*): `LangfusePromptAdapter` (primário, com `cache_ttl_seconds` configurável e busca por `label="production"` ou `version`) e `LocalYamlPromptAdapter` (contingência e ambiente de testes, lendo de `configs/prompts/*.yaml`).
- **Rationale**:
  - Permite atualizar ou fazer rollback de prompts em produção diretamente pelo painel do Langfuse sem redeploy de código nem restart dos workers.
  - O fallback para YAML local garante que o projeto rode 100% offline em desenvolvimento/CI e nunca pare caso a API do Langfuse sofra instabilidade.
- **Alternatives considered**:
  - *Prompts hardcoded em strings Python*: Exige deploy para qualquer ajuste de texto.
  - *Prompts somente no banco local sem UI de versionamento*: Perde a rastreabilidade nativa entre versão do prompt e métricas de qualidade/custo que o Langfuse já entrega pronta.

