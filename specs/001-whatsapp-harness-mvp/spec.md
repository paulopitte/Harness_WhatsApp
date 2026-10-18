# Feature Specification: WhatsApp Harness MVP

**Feature Branch**: `001-whatsapp-harness-mvp`

**Created**: 2026-10-17

**Status**: Ready for Planning

**Input**: User description: "Criar o WhatsApp Harness em Python 3.13 com Clean Architecture, DDD e Ports & Adapters. Requisitos principais: (1) Borda HTTP em FastAPI com ACK 200 imediato, verificação de assinatura, normalização e trava anti-loop/rate limit; (2) Resiliência e Quarentena de Borda (Edge Retry & DLQ); (3) Fila desacoplada e agnóstica via QueuePort (implementação inicial em Postgres com SKIP LOCKED, idempotência por provider_message_id e debounce persistido via scheduled_for); (4) Worker desacoplado com claim atômico, retry com DLQ de negócio e suporte a agente Echo para testes sem LLM; (5) Ambiente testável sem custo com ConsoleMock; (6) Simulador de webhook local via CLI; (7) Cognição em LangGraph com ModelFactory agnóstica para troca fácil entre Gemini, OpenAI e Llama/Ollama; (8) RAG agnóstico via RetrieverPort integrado ao Qdrant para consulta a políticas e FAQs; (9) Dupla memória (sumarização de contexto + memória semântica); (10) Handoff para atendente humano pausando o bot na thread; (11) Observabilidade agnóstica com Langfuse para traces de LLM e logs estruturados com OpenTelemetry."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Core Ingestion, Quarentena, Fila Agnóstica e Eco Testável (Priority: P1)

Como engenheiro do sistema, preciso que a borda HTTP receba webhooks de mensagens do WhatsApp com ACK imediato, descarte duplicatas, agrupe rajadas de mensagens rápidas (debounce persistido), gerencie falhas imediatas de ingestão em uma quarentena (Edge DLQ) e enfileire o texto normalizado para ser consumido por workers assíncronos com um agente Echo e envio em console, permitindo testar toda a infraestrutura da Harness localmente a custo zero e sem depender de APIs externas.

**Why this priority**: É a espinha dorsal de engenharia da Harness. Sem a garantia de desacoplamento entre borda e worker, idempotência, debounce no banco e claim concorrente seguro, qualquer adição de LLM gerará instabilidade e custos descontrolados.

**Independent Test**: Pode ser 100% testado executando o simulador local (`scripts/send_fake_msg.py`) disparando 5 mensagens simultâneas: a borda responde HTTP 200 em menos de 100ms, o debounce agrupa o texto em um único item na fila, o worker faz claim atômico com `EchoAgent` e o `ConsoleMock` imprime a resposta no terminal, marcando o item como `done`.

**Acceptance Scenarios**:

1. **Given** um webhook válido com mensagem de texto, **When** a borda recebe a requisição, **Then** responde HTTP 200 imediatamente (< 200ms) e enfileira a mensagem em estado `pending` com `scheduled_for = now() + debounce_delay`.
2. **Given** uma rajada de 3 mensagens enviadas pelo mesmo telefone em um intervalo menor que a janela de debounce, **When** as mensagens chegam à borda, **Then** a mensagem pendente existente tem seu texto concatenado e o `scheduled_for` empurrado para frente, gerando uma única execução consolidada no worker.
3. **Given** uma entrega duplicada de um mesmo `provider_message_id`, **When** o webhook processa a mensagem, **Then** a duplicata é descartada silenciosamente com HTTP 200 sem duplicação de itens na fila.
4. **Given** um payload com assinatura inválida ou JSON corrompido que não pode ser normalizado, **When** a borda processa a requisição, **Then** grava o payload bruto na tabela de quarentena (`quarantine_inbound` / Edge DLQ) e não propaga o erro para a fila de processamento.
5. **Given** o worker ativo e um item na fila com `scheduled_for <= now()`, **When** múltiplos workers executam concorrentemente, **Then** exatamente um worker obtém o lock atômico (`SKIP LOCKED`), executa o agente `Echo`, imprime no `ConsoleMock` e marca a fila como `done`.

---

### User Story 2 - Cognição com LangGraph, LLM Agnóstica e Envio Outbound Real (Priority: P2)

Como usuário do WhatsApp, quero interagir com um assistente inteligente que compreenda minhas mensagens e responda com linguagem natural através do WhatsApp, permitindo que a equipe de engenharia alterne o provedor de inteligência (Google Gemini, OpenAI, Llama local) e o provedor de envio via configuração, com política de retentativa e DLQ caso o envio ou o modelo falhem.

**Why this priority**: Conecta a inteligência real à Harness, transformando o esqueleto testável em um agente funcional em produção com salvaguardas de retentativa e proteção anti-loop.

**Independent Test**: Configurar o modelo para Gemini e enviar uma pergunta via simulador; em seguida, alterar a configuração em `harness.yaml` para OpenAI e reiniciar o worker; ambas as execuções devem responder com coerência sem alterar nenhuma linha do pipeline do worker.

**Acceptance Scenarios**:

1. **Given** uma mensagem normalizada puxada da fila, **When** o worker despacha para o módulo de cognição, **Then** o grafo LangGraph é executado utilizando o modelo definido na `ModelFactory` ativa.
2. **Given** uma falha temporária de rede ou rate limit no provedor de envio outbound ou na LLM, **When** o pipeline detecta o erro, **Then** incrementa `attempts`, aplica backoff exponencial e re-enfileira o item como `pending`.
3. **Given** uma mensagem que falhou 3 vezes consecutivas (limite máximo de retries), **When** a última tentativa é frustrada, **Then** o item é marcado como `dead` (Business DLQ) com o traceback gravado para inspeção.
4. **Given** um número de telefone que envia mensagens em frequência anômala acima do limite configurado (possível loop bot-to-bot), **When** a borda detecta o abuso, **Then** rejeita o processamento de novas chamadas daquele remetente temporariamente.

---

### User Story 3 - Dupla Memória, RAG Corporativo Agnóstico (PGVector/Qdrant) e Tratamento de Mídia (Priority: P3)

Como cliente com histórico contínuo de atendimento, quero que o assistente lembre dos meus dados cadastrais e preferências de conversas passadas, consiga responder dúvidas sobre políticas e documentos da empresa com base em dados atualizados usando RAG no Postgres (PGVector) ou Qdrant de forma intercambiável, e consiga processar quando eu enviar mensagens de áudio ou fotos de documentos.

**Why this priority**: O WhatsApp é um canal contínuo (não há botão de "novo chat"); sem sumarização, o contexto estoura o orçamento de tokens. Sem RAG, o agente alucina sobre regras da empresa; usando o Postgres (PGVector) como padrão inicial, unificamos a infraestrutura do MVP em um único banco, mantendo a porta do LangChain 100% agnóstica para troca futura para Qdrant, Chroma ou Pinecone.

**Independent Test**: Inserir um documento de FAQ na coleção de vetores do Postgres; enviar uma mensagem de áudio pelo simulador perguntando sobre o FAQ; a borda transcreve o áudio para texto, a fila recebe o texto transcrito, o agente executa a ferramenta de busca via `RetrieverPort`, resgata a política e responde com precisão citando as regras. Alternar a configuração para Qdrant ou mock em memória e verificar a mesma capacidade de resposta sem alterar o código do agente.

**Acceptance Scenarios**:

1. **Given** uma conversa extensa cujo histórico atinge o limite de tokens configurado, **When** o agente é invocado, **Then** o middleware de sumarização condensa as mensagens antigas em um sumário executivo, preservando a janela de contexto recente intacta.
2. **Given** um usuário que revela uma preferência estável (ex.: *"meu nome é Paulo e sou de Curitiba"*), **When** o turno é concluído, **Then** o fato semântico é salvo na tabela `semantic_facts` vinculada ao telefone e injetado nos turnos futuros.
3. **Given** uma pergunta sobre regras de negócio da empresa, **When** o grafo LangGraph processa a mensagem, **Then** aciona a porta `RetrieverPort` fornecida pela `VectorStoreFactory` (com `langchain-postgres` / PGVector ativo por padrão ou Qdrant configurado), recupera os trechos mais relevantes por similaridade semântica e embasa a resposta exclusivamente neles.
4. **Given** o recebimento de uma mensagem com áudio ou imagem suportada, **When** a requisição atinge a borda, **Then** a mídia é transcrita/descrita em texto antes de gerar o `NormalizedTextMessage`, garantindo que a fila receba apenas texto.

---

### User Story 4 - Handoff Humano, Operação e Observabilidade com Langfuse (Priority: P4)

Como operador de suporte e engenheiro de confiabilidade, quero acompanhar a telemetria das conversas e latências no Langfuse e logs estruturados, pausar a atuação do agente quando um atendente humano assumir o contato no WhatsApp, e reprocessar mensagens que caíram na DLQ através de uma interface/API de administração.

**Why this priority**: Garante governança, auditoria de custos e continuidade operacional de suporte em ambientes corporativos de produção.

**Independent Test**: Simular o acionamento do transbordo humano; enviar uma nova mensagem pelo simulador; verificar que a mensagem é gravada no histórico, mas não gera resposta automática da LLM; reprocessar um item marcado como `dead` via endpoint administrativo e verificar sua transição para `done`.

**Acceptance Scenarios**:

1. **Given** uma intenção explícita de falar com um humano ou acionamento pelo operador, **When** o estado da thread é alterado para `status = 'human'`, **Then** novas mensagens recebidas continuam sendo registradas no histórico, mas a fila não despacha tarefas para o agente de IA.
2. **Given** a execução de qualquer turno do grafo LangGraph, **When** a resposta é gerada, **Then** traces completos de custo, latência, tokens de entrada/saída e nós executados são enviados para o Langfuse.
3. **Given** itens com status `dead` na fila após falhas transitórias resolvidas, **When** o operador dispara o comando de reprocessamento via API administrativa, **Then** os itens voltam para o status `pending` com contador de tentativas zerado.

---

### Edge Cases

- **Queda de Conexão com o Postgres durante o Webhook:** O fast-retry em memória (estilo Polly via `tenacity`) realiza até 3 tentativas com backoff ultracurto (50ms, 100ms, 200ms). Se o banco permanecer inacessível, a borda responde HTTP 503 para acionar a política nativa de retransmissão da Meta.
- **Payload com Mídia Não Suportada (ex.: Vídeo pesado ou executável):** A borda rejeita o enfileiramento de cognição e agenda o envio de uma mensagem de texto pré-fabricada de recusa educada ao usuário, sem invocar a LLM.
- **Cliente enviando mensagens enquanto o Worker está processando o turno anterior:** Se o status da thread já for `processing`, as novas mensagens recebidas são enfileiradas com `scheduled_for` para o término da janela atual, evitando execuções encavaladas no mesmo `thread_id`.
- **Indisponibilidade temporária do Vector Store (PGVector/Qdrant) ou Langfuse:** Falhas no motor de busca vetorial ou na telemetria devem falhar de forma graciosa (*graceful degradation*), logando o erro sem derrubar o atendimento básico do cliente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE expor um endpoint HTTP POST para recebimento de webhooks do WhatsApp, retornando `HTTP 200 OK` em tempo inferior a 200ms sob condições normais de carga.
- **FR-002**: A borda DEVE validar a assinatura criptográfica (`X-Hub-Signature-256`) do webhook antes de aceitar o payload em ambientes de produção.
- **FR-003**: A borda DEVE implementar política de Fast-Retry em memória para absorver micro-interrupções de conexão com o banco de dados.
- **FR-004**: O sistema DEVE conter uma tabela de Quarentena / Edge DLQ (`quarantine_inbound`) para armazenar payloads brutos que não puderam ser normalizados ou validados, sem interromper o fluxo do webhook.
- **FR-005**: O sistema DEVE garantir idempotência descartando silenciosamente mensagens com `provider_message_id` já existente no banco de dados.
- **FR-006**: O sistema DEVE implementar debounce persistido no banco de dados: mensagens subsequentes da mesma thread dentro da janela de tolerância DEVEM ser concatenadas, atualizando o campo `scheduled_for`.
- **FR-007**: A fila DEVE operar sob a abstração `QueuePort` (`QueueEnqueuerProtocol` e `QueueConsumerProtocol`), permitindo substituição do PostgreSQL por RabbitMQ, Redis ou SQS sem afetar a borda nem os workers.
- **FR-008**: O worker DEVE realizar o consumo de itens da fila via lock atômico concorrente (`SKIP LOCKED`), garantindo que nenhuma mensagem seja processada por mais de um worker simultaneamente.
- **FR-009**: O worker DEVE orquestrar o ciclo de vida transacional do item: `pending` → `processing` → `done` (somente após confirmação do envio outbound) ou `dead` (após exceder o limite de retentativas).
- **FR-010**: O sistema DEVE disponibilizar uma implementação de agente `Echo` e um provedor outbound `ConsoleMock` para validação local completa sem custos de LLM ou Meta.
- **FR-011**: O sistema DEVE incluir um script de simulação CLI (`scripts/send_fake_msg.py`) para geração e disparo de eventos sintéticos de webhook.
- **FR-012**: O motor de cognição DEVE ser orquestrado via LangGraph e utilizar uma `ModelFactory` agnóstica para seleção de provedor de LLM (Google Gemini, OpenAI, Llama/Ollama) via configuração em `harness.yaml` / `.env`.
- **FR-013**: O sistema DEVE implementar uma camada agnóstica de RAG via `RetrieverPort` e `VectorStoreFactory`, utilizando `langchain-postgres` (PGVector) no mesmo banco relacional como implementação padrão do MVP, permitindo alternar de forma transparente para `Qdrant` ou outros bancos de vetores compatíveis com LangChain exclusivamente por configuração.
- **FR-014**: O sistema DEVE manter duas memórias segregadas: memória de contexto operacional com compactação/sumarização de histórico longo e memória semântica persistente de fatos do cliente.
- **FR-015**: O sistema DEVE suportar transbordo humano (Handoff), permitindo alternar a thread entre `bot` e `human`; em modo `human`, mensagens recebidas são registradas no banco sem despachar execução para a LLM.
- **FR-016**: A borda DEVE converter mensagens de áudio em texto (transcrição) e imagens em texto descritivo antes do enfileiramento, mantendo o contrato da fila estritamente textual.
- **FR-017**: O sistema DEVE enviar traces detalhados de execução para o Langfuse e registrar logs estruturados compatíveis com OpenTelemetry.
- **FR-018**: O sistema DEVE fornecer endpoints administrativos protegidos para consulta de status da fila, métricas operacionais e reprocessamento de mensagens da DLQ.

### Key Entities

- **InboundMessage**: Registro bruto da mensagem de entrada recebida do provedor, contendo metadados de transporte, timestamp e identificador único de entrega.
- **NormalizedTextMessage**: Objeto de valor do domínio contendo exclusivamente o identificador da thread, texto consolidado e metadados contextuais, agnóstico ao canal de origem.
- **QueueItem**: Entidade de controle de ciclo de vida da fila, contendo `id`, `thread_id`, `payload`, `status` (`pending`, `processing`, `done`, `dead`), `scheduled_for`, `attempts`, `last_error` e timestamps.
- **Thread**: Representação persistente da conversa identificada deterministicamente pelo telefone do usuário (`thread_id`), contendo o status de atendimento (`bot`, `human`), contadores de rate limit e sumário consolidado do histórico.
- **SemanticFact**: Fato estável aprendido sobre o usuário (chave/valor ou texto), persistido independentemente do histórico recente de mensagens.
- **QuarantineEntry**: Registro de contingência na borda contendo payload bruto, cabeçalhos HTTP, data e diagnóstico de erro para investigação técnica.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O endpoint de webhook da borda responde `HTTP 200 OK` em menos de 150 milissegundos no percentil 95 (P95) durante carga normal.
- **SC-002**: 100% das mensagens duplicadas com o mesmo identificador de provedor são descartadas sem gerar execuções duplicadas ou respostas repetidas ao usuário.
- **SC-003**: Rajadas de até 5 mensagens consecutivas de um mesmo usuário em um intervalo de 3 segundos são agrupadas em um único processamento pelo worker em 100% dos testes.
- **SC-004**: O sistema pode ser inicializado e testado ponta a ponta em ambiente local (ingestão -> fila -> eco -> console) sem necessidade de credenciais de provedor de telefonia ou chaves pagas de LLM.
- **SC-005**: A troca entre provedores de LLM (ex.: Gemini para OpenAI) e entre implementações de fila (Postgres para Mock) pode ser realizada exclusivamente via alteração de arquivo de configuração, sem modificações no código-fonte das camadas de domínio ou pipeline de worker.
- **SC-006**: Mensagens com falhas irrecuperáveis ou erros consecutivos atingem a Dead-Letter Queue (DLQ) com diagnóstico completo preservado e podem ser reprocessadas via comando administrativo com recuperação de 100% dos itens elegíveis.
- **SC-007**: Toda interação executada pelo grafo LangGraph gera um trace correspondente no Langfuse com métricas de tempo de resposta e consumo de tokens registradas.

## Assumptions

- O PostgreSQL versão 16+ com a extensão `pgvector` habilitada está disponível para persistência transacional, gerenciamento de fila via `FOR UPDATE SKIP LOCKED` e armazenamento vetorial RAG do MVP em uma infraestrutura unificada.
- A biblioteca `uv` é utilizada como gerenciador oficial de pacotes e ambientes virtuais Python 3.13+.
- A biblioteca `psycopg` (v3) em modo assíncrono com pool de conexões é a ferramenta padrão de comunicação com o PostgreSQL.
- O cluster Qdrant e outros provedores de vector store do LangChain permanecem suportados como adaptadores plugáveis via `VectorStoreFactory` sem alterações de código no agente.
- A comunicação com o WhatsApp em produção poderá utilizar a API Oficial da Cloud (Meta) ou provedores de mercado (Evolution API / Z-API) através da implementação de adaptadores que respeitam a porta `OutboundProviderProtocol`.
- As mensagens de mídia suportadas no MVP compreendem áudio (formato ogg/opus ou mp3) e imagem (jpeg/png); formatos não suportados são descartados na borda com resposta informativa fixa.

