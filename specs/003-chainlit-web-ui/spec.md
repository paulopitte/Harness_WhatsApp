# Feature Specification: Interface Web Interativa com Chainlit (003-chainlit-web-ui)

> **Spec-Driven Development (SpecKit) — Fase 3 da WhatsApp AI Harness**  
> *Baseado em Clean Architecture, Domain-Driven Design (DDD), SOLID e Ports & Adapters.*

---

## 🎯 Visão Geral do Produto

Esta especificação define a criação de uma **Interface Web Interativa de Chat (UI)** moderna e pronta para demonstrações, testes visuais e homologação corporativa utilizando o framework **Chainlit**:
1. **Reutilização Integral do Núcleo da Harness:** A UI Web consome o mesmo motor de cognição (`LangGraphCognitionEngine`), RAG vetorial no PostgreSQL (`knowledge_documents`), Dupla Memória Semântica e PromptOps (`Langfuse`).
2. **Ambiente Visual Plug-and-Play para Clientes e Demonstrações:** Permite que clientes e avaliadores conversem com o agente diretamente no navegador web sem precisar de número do WhatsApp ou Postman.
3. **Observabilidade e Tracing no Chainlit:** Exibição visual dos passos e ferramentas acionadas pelo LangGraph (RAG, buscas, analista) na barra lateral do chat.
4. **Isolamento de Processo (Processo 4):** A aplicação Chainlit roda de forma desacoplada em sua própria porta (ex.: `8002`), sem interferir na Borda (`8000`), nos Workers de Fila ou na Admin API (`8001`).

---

## 👥 Histórias de Usuário & Critérios de Aceite (Gherkin)

### User Story 1 (P1): Sessão de Chat Interativa no Navegador
> **Como** cliente, avaliador ou desenvolvedor,  
> **Quero** acessar o navegador em `http://localhost:8002`,  
> **Para que** eu possa conversar com o agente de IA visualmente como se estivesse no WhatsApp ou ChatGPT.

#### Cenário 1.1: Inicialização da Sessão Web
* **Given** que o servidor Chainlit foi iniciado via `uv run chainlit run scripts/run_chainlit.py`,
* **When** o usuário abre `http://localhost:8002` no navegador,
* **Then** uma tela de boas-vindas com o nome do assistente corporativo é renderizada,
* **And** uma sessão única (`thread_id="web_{session_id}"`) é associada ao usuário.

#### Cenário 1.2: Envio de mensagem e resposta do agente
* **Given** que a sessão está ativa,
* **When** o usuário envia *"Olá, quais os perfumes e fragrâncias disponíveis?"*,
* **Then** o Chainlit invoca `container.cognition_engine.generate_reply(thread_id, text)`,
* **And** exibe a resposta formatada em Markdown com o catálogo e fontes semânticas.

---

### User Story 2 (P2): Persistência da Dupla Memória Semântica na Web
> **Como** usuário da interface web,  
> **Quero** informar meus dados pessoais (nome, preferências) no chat,  
> **Para que** nas mensagens seguintes o agente lembre de mim da mesma forma que faz no WhatsApp.

#### Cenário 2.1: Continuidade de Memória Semântica
* **Given** que na primeira mensagem o usuário informou *"Meu nome é Paulo e prefiro notas amadeiradas"*,
* **When** na mensagem seguinte o usuário perguntar *"Qual o meu nome e o que eu prefiro?"*,
* **Then** o motor consulta a memória semântica persistida no PostgreSQL,
* **And** responde citando o nome Paulo e a preferência por notas amadeiradas.

---

## 🔒 Requisitos Não-Funcionais

1. **Desacoplamento Arquitetural (NFR-001):** O script `scripts/run_chainlit.py` consome apenas o container oficial da aplicação (`build_container(cfg)`), mantendo Clean Architecture sem duplicação de regras.
2. **Suporte a Windows SelectorEventLoop (NFR-002):** A integração com o pool `psycopg` v3 no Windows deve operar harmoniosamente com o event loop assíncrono do Chainlit.

