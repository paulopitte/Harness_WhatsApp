<!--
Sync Impact Report:
- Version change: 1.0.0 → 1.1.0
- Added/Modified principles:
  - I. Arquitetura de Harness, DDD e Isolamento de Processos (integrado Ubiquitous Language, Bounded Contexts, Aggregates/Value Objects)
  - II. Engenharia de Software: SOLID, Clean Code, KISS e YAGNI (novo princípio explícito detalhando aplicação prática em Python 3.13)
  - III. Contrato Único de Fila e Fronteira Multimodal
  - IV. Identidade de Thread, Debounce e Dupla Memória
  - V. Tipagem Forte, Validação e Controle Estrito de Dependências
  - VI. Ciclo de Vida da Fila, Confirmação Outbound e Retry (DLQ)
  - VII. Cobertura de Testes Obrigatória e Desenvolvimento Incremental
  - VIII. Observabilidade, Configuração Hierárquica e Segredos
- Templates aligned:
  - ✅ .specify/templates/plan-template.md
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
- Follow-up TODOs: None
-->
# WhatsApp Harness MVP Constitution

## Core Principles

### I. Arquitetura de Harness, DDD (Domain-Driven Design) e Isolamento de Processos
O sistema NÃO é "um script de agente com um webhook", mas uma **Harness de Produção** guiada por **DDD** e executada em três processos independentes (`webhook`, `worker`, `admin`), respeitando *Bounded Contexts* (Contextos Delimitados) claros:
- **`domain/` (Core Domain & Ubiquitous Language)**: Coração do negócio. Contém Entidades, *Value Objects* imutáveis (ex.: `ThreadId`, `PhoneNumber`), Agregados, Eventos de Domínio (`DomainEvent`), Enums de estado (`pending`, `processing`, `done`, `dead`), Exceções de Domínio e *Ports/Interfaces* (`typing.Protocol`). DEVE ter zero dependências de frameworks HTTP, banco de dados, provedores de WhatsApp ou LLMs.
- **`edge/` (Inbound ACL - Anti-Corruption Layer)**: Borda HTTP. Atua como *Camada Anticorrupção*, traduzindo payloads externos sujos da Meta/provedores para a linguagem ubíqua do nosso domínio (`InboundMessage` -> `NormalizedTextMessage`), respondendo ACK (`HTTP 200 OK`) imediato, validando assinatura, aplicando rate limit e convertendo mídia em texto antes da fila.
- **`ingress/` & `persistence/` (Infrastructure Adapters)**: Implementações concretas de fila e repositórios no Postgres.
- **`workers/` (Application Orchestration)**: Processamento assíncrono horizontal. Faz *claim* atômico da fila (`SKIP LOCKED`), coordena o fluxo de aplicação (Use Cases) entre domínio, cognição e envio outbound.
- **`cognition/` (Bounded Context de Inteligência)**: Único módulo autorizado a conversar com LLMs/grafos (LangChain v1 / LangGraph). Exporta uma fachada/interface limpa de grafo para o worker.
- **`outbound/` (Outbound ACL)**: Camada isolada de envio de mensagens para o provedor em nova conexão HTTP.
- **`ops/`**: Telemetria operacional, API administrativa e segurança.

**Regras de Isolamento**:
- Endpoints HTTP (`edge/webhook.py`) NUNCA devem invocar o grafo de cognição (`cognition/`) diretamente no ciclo da requisição do webhook.
- O módulo `cognition/` NUNCA deve conhecer detalhes do provedor de canal (Meta, Z-API, Evolution) nem acessar payloads brutos do webhook.

*Rationale*: Protege o domínio contra vazamento de infraestrutura (DDD Anti-Corruption Layer), evita perda silenciosa de mensagens em picos de tráfego e permite escalar borda e workers de forma independente.

### II. Engenharia de Software: SOLID, Clean Code, KISS e YAGNI
Todo código escrito neste repositório DEVE obedecer explicitamente aos princípios abaixo:
- **SOLID em Python 3.13**:
  - **S (Single Responsibility)**: Cada módulo, classe ou função deve ter uma única razão para mudar (ex.: `webhook.py` só recebe HTTP; `normalize.py` só limpa payload; `postgres_queue.py` só gerencia fila).
  - **O (Open/Closed)**: Comportamentos variáveis (novos agentes em `cognition/agents/`, novos provedores em `outbound/providers/` ou conversores de mídia) DEVEM ser extensíveis via registro/polimorfismo sem modificar o código do pipeline do worker.
  - **L (Liskov Substitution)**: Qualquer implementação de um `Protocol` (ex.: `ConsoleOutboundProvider` vs. `MetaOutboundProvider`) DEVE ser 100% intercambiável sem quebrar contratos ou expectativas de retorno.
  - **I (Interface Segregation)**: Interfaces (`typing.Protocol`) DEVEM ser pequenas e coesas (ex.: separar `QueueEnqueuerProtocol` usado pela borda de `QueueConsumerProtocol` usado pelo worker).
  - **D (Dependency Inversion)**: Módulos de alto nível (`workers/`, `edge/`) NUNCA devem depender de implementações concretas de baixo nível (`postgres_queue.py`, `meta.py`), mas sim de abstrações (`Protocol`) injetadas na raiz de composição (`app.py`).
- **Clean Code**:
  - Funções pequenas, coesas, com nomes reveladores de intenção e no máximo um nível de responsabilidade.
  - Proibido o uso de *magic numbers* ou *magic strings* soltos no código (usar Enums, constantes nomeadas ou configurações tipadas do `harness.yaml`).
  - *Early Return / Guard Clauses* no lugar de `if/else` profundamente aninhados.
- **KISS (Keep It Simple, Stupid)**:
  - A solução mais simples, legível e direta que respeita as fronteiras da arquitetura SEMPRE vence a solução complexa ou "esperta demais".
- **YAGNI (You Aren't Gonna Need It)**:
  - É PROIBIDO criar infraestrutura especulativa não exigida pela fase atual do MVP (ex.: não criar brokers Kafka/RabbitMQ, microsserviços distribuídos, multi-tenancy complexo ou frameworks genéricos antes da necessidade real comprovada).

*Rationale*: Equilibra o rigor arquitetural corporativo (SOLID/DDD/Clean Code) com o pragmatismo de entrega de um MVP (KISS/YAGNI), impedindo tanto o "código espaguete" quanto o *over-engineering*.

### III. Contrato Único de Fila e Fronteira Multimodal
A fila de processamento (`ingress/`) aceita EXCLUSIVAMENTE itens de texto normalizados (`NormalizedTextMessage`):
- **Mídia morre na borda**: Áudio (transcrição) e Imagem (visão para texto) DEVEM ser convertidos em texto estruturado em `edge/media/` antes do enfileiramento.
- **Formatos não suportados**: Vídeos ou documentos não suportados DEVEM ser recusados na borda com resposta fixa padronizada, sem acionar a fila de cognição nem consumir LLM principal.
- **Idempotência**: Todo item recebido DEVE ser validado contra `provider_message_id` único para descartar entregas duplicadas do provedor de WhatsApp.

*Rationale*: Simplifica o agente principal (que passa a ser puramente textual), reduz drasticamente o custo de tokens no histórico da conversa e torna o motor de cognição facilmente substituível e testável.

### IV. Identidade de Thread, Debounce e Dupla Memória
No WhatsApp não existe o conceito de "nova sessão de chat" criada pelo usuário; a identidade da conversa (`thread_id`) é um *Value Object* derivado de forma determinística a partir do telefone normalizado (ou seu hash):
- **Debounce Obrigatório**: Mensagens fragmentadas enviadas em sequência rápida pelo mesmo `thread_id` (ex.: *"oi"* + *"tudo bem?"*) DEVEM ser agrupadas em um único turno de processamento antes do claim definitivo do worker.
- **Dois Tipos de Memória**:
  1. **Memória Operacional/Contexto (`context.py` + `thread_store.py`)**: Histórico recente da thread com compactação/sumarização automática quando atingir o limite de tokens configurado.
  2. **Memória Semântica (`semantic_memory.py`)**: Fatos estáveis sobre o usuário extraídos e persistidos em tabela dedicada, independentes da janela de sumarização da conversa.

*Rationale*: Impede execuções concorrentes e respostas encavaladas para rajadas de mensagens curtas, mantendo o custo de contexto sob controle em conversas que duram meses.

### V. Tipagem Forte, Validação e Controle Estrito de Dependências
O projeto adota **Python Estrito (estilo C#/.NET)**:
- **Type Hints Obrigatórios**: Todas as funções, métodos e atributos DEVEM possuir anotações explícitas de tipo (Python 3.13+). O uso de `dict[str, Any]` solto entre camadas é PROIBIDO; toda fronteira entre módulos DEVE trafegar modelos `Pydantic` (`BaseModel`) ou `dataclass(frozen=True)`.
- **Validação na Entrada**: Todo payload externo ou comando de entrada DEVE ser validado imediatamente via Pydantic v2 (`ConfigDict(strict=True)` quando aplicável), traduzindo erros para respostas padronizadas em português.
- **Controle de Dependências**: Além dos pacotes homologados na seção **Stack Tecnológica**, nenhuma nova biblioteca externa PODE ser adicionada ao `pyproject.toml` sem justificativa explícita aprovada no `plan.md`.

*Rationale*: Traz a segurança de compilação, autocompletar e contratos explícitos do ecossistema .NET para o Python, evitando erros em tempo de execução e inchaço de pacotes (*dependency bloat*).

### VI. Ciclo de Vida da Fila, Confirmação Outbound e Retry (DLQ)
WhatsApp não utiliza streaming de tokens; toda resposta segue um ciclo transacional estrito:
- **Estados da Fila**: `pending` → `processing` → `done` | `dead`.
- **Confirmação Real**: Um item da fila SÓ pode ser marcado como `done` após o módulo `outbound/` confirmar o envio HTTP com sucesso junto ao provedor.
- **Política de Retry e Dead-Letter**: Em caso de falha no processamento ou no envio outbound, o item DEVE retornar para a fila com incremento de tentativas (`attempts`) e backoff, até o limite configurado em `harness.yaml` (ex.: 3 tentativas). Esgotadas as tentativas, o item DEVE ser marcado como `dead` com o erro registrado para inspeção no painel admin.

*Rationale*: Garante que nenhuma mensagem de cliente seja perdida silenciosamente caso a LLM ou a API da Meta oscilem.

### VII. Cobertura de Testes Obrigatória e Desenvolvimento Incremental
A implementação DEVE respeitar a ordem arquitetural (Borda/Fila/Worker Eco antes da LLM):
- Toda regra de domínio, normalização, debounce, claim atômico de fila e transição `retry -> dead` DEVE possuir testes automatizados com `pytest`.
- O sistema DEVE ser validável ponta a ponta localmente usando um provedor mock/console e um agente "Echo" antes de acoplar credenciais reais da Meta ou chamadas pagas de LLM.

*Rationale*: Permite validar a robustez da engenharia da Harness (concorrência, locks e retries) de forma rápida, determinística e gratuita.

### VIII. Observabilidade, Configuração Hierárquica e Segredos
- **Hierarquia de Configuração**: Precedência estrita gerenciada via `pydantic-settings`: `configs/harness.yaml` (comportamento operacional: debounce ms, retries, modelos, flags de mídia) → Variáveis de Ambiente / `.env` (segredos e infraestrutura).
- **Segredos**: Chaves de LLM, tokens da Meta e *connection strings* NUNCA devem ser versionados no repositório (apenas `.env.example` documentado).
- **Telemetria Operacional**: Transições de estado da fila (`received`, `debounced`, `queued`, `claimed`, `completed`, `retried`, `dead`) e execuções de agentes (`runs`) DEVEM gerar eventos estruturados com `correlation_id`/`thread_id` persistidos para auditoria e consulta na `admin_api`.

*Rationale*: Dá visibilidade total sobre gargalos de fila, custos e falhas em produção sem depender exclusivamente de logs de console.

## Stack Tecnológica

- **Linguagem & Gerenciador**: Python 3.13+ gerenciado exclusivamente via `uv` (`pyproject.toml` + `uv.lock`).
- **Web & APIs (Edge & Admin)**: FastAPI + Uvicorn.
- **Modelagem, Validação & Config**: Pydantic v2 + Pydantic Settings + PyYAML.
- **Persistência & Fila (MVP)**: PostgreSQL (via `psycopg[binary,pool]` v3 assíncrono) para fila (`SKIP LOCKED`), histórico de threads, fatos semânticos e eventos operacionais.
- **Cliente HTTP Outbound**: `httpx` (assíncrono).
- **Cognição & Agentes**: LangChain v1 / LangGraph.
- **Qualidade & Testes**: `pytest`, `pytest-asyncio`, `ruff` (linter/formatter Clean Code) e `mypy` ou `pyright` (checagem estática de tipos).

## Convenções de Código, Nomenclatura e Versionamento

- **Idioma**:
  - Nomes de pacotes, módulos, classes, funções, variáveis e colunas de banco de dados DEVEM ser escritos em **inglês** (`snake_case` para funções/variáveis/arquivos, `PascalCase` para classes/modelos Pydantic/Protocols, `UPPER_SNAKE_CASE` para constantes).
  - Mensagens de retorno ao usuário final (WhatsApp), erros de validação expostos na API e comentários/docstrings didáticos do projeto DEVEM ser escritos em **português**.
- **Nomenclatura Arquitetural (DDD & SOLID)**:
  - **Ports/Protocols (Interfaces)**: Sufixo `Protocol` ou `Port` (ex.: `QueueEnqueuerProtocol`, `QueueConsumerProtocol`, `OutboundProviderProtocol`).
  - **Entidades / Value Objects / DTOs**: `InboundWebhookPayload`, `NormalizedTextMessage`, `QueueItem`, `ThreadId`, `PhoneNumber`.
  - **Use Cases / Services**: Verbos claros indicando a ação única (ex.: `IngestWebhookUseCase`, `ProcessQueueItemPipeline`).
  - **Exceções de Domínio**: Sufixo `Error` (padrão Pythonico equivalente ao `Exception` do C#), herdando de `HarnessDomainError` (ex.: `RateLimitExceededError`, `UnsupportedMediaError`, `OutboundDeliveryError`).
- **Git Branches**: `feature/[FASE-ID]-short-description` ou `fix/[FASE-ID]-short-description`.
- **Padrão de Commits**: Formato `<tipo>(<escopo>): <descrição> [<FASE/TASK>]` (ex.: `feat(edge): implementa normalizacao e ack do webhook [FASE-01]`).

## Governance

- **Supremacia da Constituição**: Esta constituição tem precedência sobre qualquer `spec.md`, `plan.md` ou `tasks.md`. Caso um plano sugira chamar a LLM na borda, violar SOLID/DDD ou introduzir complexidade desnecessária que fira KISS/YAGNI, o plano DEVE ser rejeitado e corrigido.
- **Processo de Emenda**: Qualquer alteração nos princípios ou na Stack Tecnológica exige atualização prévia desta constituição com incremento de versão antes de modificar o código.
- **Política de Versionamento**: Versionamento Semântico (`MAJOR.MINOR.PATCH`):
  - `MAJOR`: Remoção ou quebra de isolamento entre Borda, Fila, Worker e Cognição.
  - `MINOR`: Adição de novo princípio, camada ou dependência homologada na stack.
  - `PATCH`: Refinamentos de texto, exemplos didáticos ou ajustes de nomenclatura.

**Version**: 1.1.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17

