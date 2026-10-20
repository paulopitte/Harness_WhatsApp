# Feature Specification: Painel de Controle (Frontend)/UI (004-control-plane-ui)

> **Spec-Driven Development (SpecKit) — Fase 4 da WhatsApp AI Harness**  
> *Baseado em Clean Architecture, Domain-Driven Design (DDD), SOLID e Ports & Adapters.*  
> *Diretório alvo do Frontend: `frontend/`*  
> *Diretrizes Visuais & UX: Aplicadas conforme a skill `frontend-design`.*  
> *Diretrizes de Performance React & Next.js: Vercel Engineering Best Practices (`vercel-react-best-practices`).*

---

## 🎯 1. Visão Geral do Produto & Identidade Visual

Esta especificação define o desenvolvimento da interface web administrativa corporativa (**Control Plane UI** / Backoffice SaaS) da **WhatsApp AI Harness**.

### 💼 Contexto, Audiência e Propósito
* **O que é o produto:** Um cockpit de controle operacional para gestão em tempo real de agentes de IA conversacionais que atendem no WhatsApp em escala empresarial.
* **Público-alvo:** Operadores de suporte e vendas (que precisam intervir em conversas críticas sem hesitação), engenheiros de IA/SREs (que monitoram filas, retries e custos) e gestores de atendimento (que acompanham indicadores de conversão e segurança).
* **Trabalho principal da interface:** Proporcionar **consciência situacional instantânea** e **intervenção sem atrito** — permitir que um operador assuma um cliente com 1 clique tendo a memória do cliente à vista, ou que um engenheiro reponha uma mensagem travada na DLQ com 1 clique.

### 🎨 Princípios de Design & Identidade (Skill `frontend-design`)
Para evitar a aparência genérica de templates de IA ("SaaS-card kit" com gradientes roxos e cards com sombras idênticas), adotamos uma identidade visual com **ponto de vista próprio**:

1. **Estética de Cockpit Operacional (Industrial & Preciso):**
   - Fundo em ardósia profunda (`#0B0F19` / `#111827`) com contraste nítido, dispensando gradientes decorativos ou sombras difusas.
   - Densidade de informação balanceada para operação contínua em telas de suporte.
   - Linhas de divisão com bordas sutis (`border-slate-800`) e cantos discretos (`rounded-md`, 6px), sem cartões flutuantes desnecessários.
2. **Paleta de Cores com Função Específica:**
   - **Base Profunda:** `#0B0F19` (Canvas principal) e `#111827` (Superfície dos painéis e listas).
   - **Bordas & Divisores:** `#1F2937` (Delimitação estrutural).
   - **Acento Operacional WhatsApp:** `#10B981` (Verde esmeralda para status ativo, bot online e confirmações).
   - **Atenção Crítica / Handoff / DLQ:** `#F43F5E` (Carmim para erros, mensagens mortas e alertas de injeção).
   - **Intervenção Humana:** `#F59E0B` (Âmbar para conversas que exigem atenção de um atendente).
   - **Tipografia:** `#F8FAFC` (Texto principal) e `#94A3B8` (Metadados e rótulos secundários).
3. **Tipografia Disciplinada & Microcópia Ativa:**
   - Tipografia primária: `Geist Sans` ou `Inter` com escala harmônica e comprimento de linha rigorosamente inferior a 75 caracteres.
   - Tipografia monoespaçada: `Geist Mono` ou `JetBrains Mono` reservada **estritamente** para dados computacionais: números E.164 (`+55 11 99999-8888`), identificadores de fila, payloads JSON e timestamps.
   - **Sem rótulos em CAIXA ALTA** desnecessários e sem palavras isoladas em itálico/destaque colorido em títulos.
   - Textos de ação diretos e no imperativo ("Assumir conversa", "Devolver ao assistente", "Reprocessar mensagem", "Salvar alterações").

---

## ⚡ 2. Princípios de Performance Vercel Engineering (`vercel-react-best-practices`)

O frontend é projetado para máxima performance em produção, seguindo as diretrizes oficiais de engenharia da Vercel:

1. **Eliminação Radical de Waterfalls (`async-`):**
   - Requisições paralelas com `Promise.all` e limites estratégicos de streaming via `<Suspense fallback={<Skeleton />}>`.
   - Carregamento instantâneo do Shell da aplicação antes de aguardar dados da rede.
2. **Otimização Extrema de Bundle (`bundle-`):**
   - **Proibição de Barrel Files (`bundle-barrel-imports`):** Importações diretas dos módulos específicos (ex.: `@/components/ui/button` em vez de `@/components/ui`).
   - **Imports Dinâmicos (`bundle-dynamic-imports`):** Componentes pesados (como o editor de YAML de Prompts ou visualizadores de JSON) carregados sob demanda via `next/dynamic({ ssr: false })`.
3. **Gerenciamento de Estado do Cliente e Deduplicação (`client-`):**
   - Adoção de **SWR (`client-swr-dedup`)** para cache inteligente, revalidação em background e deduplicação automática de requisições concorrentes da Admin API.
4. **Otimização de Re-renderizações (`rerender-`):**
   - **Cálculo de Estado Derivado no Render (`rerender-derived-state-no-effect`):** Proibido sincronizar estados calculáveis dentro de `useEffect`.
   - **Transições Não-Urgentes (`rerender-transitions`):** Uso de `useTransition` / `startTransition` na digitação de filtros e buscas de conversas para manter a digitação fluida a 60fps.
   - **Proibição de Componentes Inline (`rerender-no-inline-components`):** Todo sub-componente é extraído do escopo para evitar remontagens desnecessárias da árvore DOM.
5. **Performance de Renderização (`rendering-`):**
   - Renderização condicional estrita via operadores ternários (`condition ? <Component /> : null`), evitando `condition && <Component />` que pode renderizar `0` indesejado.
   - Uso de `content-visibility: auto` (`rendering-content-visibility`) na listagem de centenas de conversas do WhatsApp para acelerar o layout do navegador.

---

## 👥 3. Histórias de Usuário & Critérios de Aceite (Gherkin)

### User Story 1 (P1): Atendimento em Tempo Real e Handoff Humano (Split-View em 3 Colunas)
> **Como** atendente de suporte ou operador de plantão,  
> **Quero** visualizar a lista de conversas, o chat ao vivo e a memória do cliente lado a lado,  
> **Para que** eu possa assumir conversas sensíveis imediatamente e ter o contexto completo do cliente sem mudar de tela.

#### Cenário 1.1: Layout de Atendimento em 3 Colunas com Suspense
* **Given** que o atendente acessa o módulo *"Conversas"*,
* **When** a rota é carregada,
* **Then** o esqueleto visual (Skeleton) é exibido instantaneamente via Suspense,
* **And** a interface apresenta um layout de 3 colunas:
  1. **Coluna 1 (Lista de Threads - 320px):** Lista ordenada por recência com `content-visibility: auto`, avatar, telefone E.164, trecho da última mensagem e tag de estado (`IA ativa`, `Aguardando humano`, `Em pausa`).
  2. **Coluna 2 (Chat Ativo - Flexível):** Histórico de mensagens com balões estilizados, indicação clara de remetente (Cliente / IA / Humano) e barra de status superior.
  3. **Coluna 3 (Inteligência do Cliente - 340px):** Perfil Semântico persistido no PostgreSQL (nome detectado, preferências, intenção e resumo executivo da conversa).

#### Cenário 1.2: Intervenção Humana (Handoff) com 1 Clique e Mutação Otimista
* **Given** que a thread selecionada está em modo `bot`,
* **When** o operador clica no botão *"Assumir conversa"*,
* **Then** a interface atualiza o estado otimista imediatamente via SWR,
* **And** o frontend dispara `POST /admin/threads/{id}/handoff` com payload `{"mode": "human"}`,
* **And** o status visual muda para o tom âmbar *"Em atendimento por operador"*,
* **And** o campo de digitação do operador é habilitado no rodapé do chat,
* **And** o Worker assíncrono do backend silencia o bot imediatamente para essa thread.

#### Cenário 1.3: Devolução ao Assistente de IA
* **Given** que a conversa está em modo `human`,
* **When** o operador clica em *"Devolver ao assistente"*,
* **Then** a thread retorna para o modo `bot`,
* **And** as próximas mensagens do cliente no WhatsApp voltam a ser respondidas pelo LangGraph.

---

### User Story 2 (P1): Monitoramento Operacional da Fila e Replay de Mensagens Mortas (DLQ)
> **Como** engenheiro de SRE ou suporte de infraestrutura,  
> **Quero** acompanhar o fluxo das mensagens na fila e os itens mortos na DLQ,  
> **Para que** eu possa auditar gargalos da Meta API e reenviar mensagens com falha com segurança total.

#### Cenário 2.1: Visualização dos Estados da Fila com Auto-Refresh
* **Given** que o operador acessa *"Fila & DLQ"*,
* **When** a página carrega,
* **Then** 4 indicadores de topo exibem contagens em tempo real (`pending`, `processing`, `done`, `dead`),
* **And** uma tabela de alta densidade lista as mensagens com ID, Telefone (mono), Tentativas (3/3), Data e Causa da Falha.

#### Cenário 2.2: Replay Transacional de Mensagem Morta
* **Given** que há mensagens na DLQ decorrentes de indisponibilidade externa temporária,
* **When** o operador clica em *"Reprocessar"* no item da tabela,
* **Then** o backend reseta o status para `pending` com `retry_count = 0` e `scheduled_for = now()`,
* **And** a mensagem é reprocessada pelo Worker na próxima rodada, saindo da lista de erros.

---

### User Story 3 (P2): Dashboard Executivo com Consciência Situacional
> **Como** gestor da operação,  
> **Quero** uma visão sintética e não poluída dos principais indicadores do sistema,  
> **Para que** eu possa avaliar a saúde geral do atendimento em segundos.

#### Cenário 3.1: Visualização de Métricas Reais Sem Waterfalls
* **Given** que o gestor entra no Dashboard,
* **When** a página é carregada,
* **Then** as métricas são buscadas em paralelo via `Promise.all` no SWR,
* **And** os blocos analíticos limpos são renderizados:
  - **Volume de Atendimentos:** Total de mensagens recebidas no dia e média por hora.
  - **Eficiência Cognitiva:** Latência média da IA (em segundos) e taxa de sucesso nas respostas.
  - **Distribuição de Atendimento:** Proporção de conversas Bot vs Humano.
  - **Saúde dos Serviços:** Indicadores de pulso da Borda FastAPI, PostgreSQL, Qdrant e Provedor LLM.

---

### User Story 4 (P2): Central de Segurança e Auditoria de Guardrails
> **Como** responsável por conformidade e segurança (Compliance),  
> **Quero** auditar mensagens bloqueadas por injeção de prompt ou conteúdo impróprio,  
> **Para que** eu identifique vulnerabilidades ou tentativas de abuso do sistema.

#### Cenário 4.1: Log de Bloqueios de Segurança
* **Given** que uma tentativa de injeção de prompt ou linguagem proibida foi barrada pelo middleware de segurança (`RunStatus.BLOCKED`),
* **When** o usuário consulta a aba *"Segurança"*,
* **Then** o evento é exibido com carimbo de data/hora, número mascarado, tipo de violação e trecho identificado pelo filtro.

---

### User Story 5 (P3): Gestão de Agentes e Configuração de Cognição
> **Como** arquiteto de IA,  
> **Quero** ajustar o modelo ativo, instruções do prompt de sistema e ativar/desativar a Pesquisa Profunda (Deep Research),  
> **Para que** eu calibre as respostas do assistente conforme o momento do negócio.

#### Cenário 5.1: Controle das Ferramentas Cognitivas e Editor Dinâmico
* **Given** que a Pesquisa Profunda (Deep Research) está desativada por padrão,
* **When** o usuário acessa *"Agentes"*, ativa a opção *"Pesquisa Profunda na Web (DuckDuckGo)"* e clica em *"Salvar alterações"*,
* **Then** o editor de YAML (carregado dinamicamente via `next/dynamic`) atualiza as instruções,
* **And** novas dúvidas que extrapolem o catálogo passam a ativar o sub-motor de pesquisa web.

---

## 🔒 4. Requisitos Não-Funcionais (NFRs)

1. **Isolamento Absoluto (NFR-001):** O frontend residirá integralmente no diretório `frontend/`. Nenhuma dependência `npm` contamina o ecossistema Python do projeto raiz.
2. **Autenticação via Header Padronizado (NFR-002):** Toda chamada para a Admin API (`http://localhost:8001`) envia o header `X-Admin-Api-Key` com o token definido em `.env.local`.
3. **Tratamento de Falhas e Estados Vazios (NFR-003):** Nenhuma tela apresenta erros vagos. Telas vazias oferecem orientação e convite à ação ("Nenhuma conversa pendente. Novas mensagens do WhatsApp aparecerão aqui automaticamente.").
4. **Performance e Acessibilidade (NFR-004):** Respeito a `prefers-reduced-motion`, contraste de cores em conformidade com WCAG AA, navegação fluida por teclado e 0 waterfalls de requisição.
