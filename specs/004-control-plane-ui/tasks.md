# Tasks: Painel de Controle Empresarial (004-control-plane-ui)

> **SpecKit — Checklist de Tarefas (TDD, Design-Driven & Vercel Best Practices)**  
> *Continuidade sequencial a partir da Tarefa T066 da Fase 3.*  
> *Diretório alvo do Frontend: `frontend/`*  
> *Diretrizes: Alinhadas com `frontend-design` e `vercel-react-best-practices`.*

---

## 📋 Lista de Tarefas (P1 a P3)

### Fase 1: Setup do Projeto, Tokens de Design e Camada de Dados (P1)
- [ ] **T067**: Inicializar o projeto `frontend/` com **Next.js 15 (App Router)**, **TypeScript**, **Tailwind CSS** e dependências centrais:
  - Instalar `swr` (`client-swr-dedup`), `lucide-react`, `clsx`, `tailwind-merge` e `next-themes`.
- [ ] **T068**: Configurar o **Sistema de Tokens de Design** em `frontend/src/app/globals.css` e `tailwind.config.ts`:
  - Definir variáveis CSS estruturais (`--bg-canvas`, `--bg-surface`, `--border-subtle`, `--status-active`, `--status-attention`, `--status-critical`).
  - Configurar tipografia com `Geist Sans` para leitura e `Geist Mono` estritamente para números E.164 e identificadores.
- [ ] **T069**: Implementar componentes atômicos em `frontend/src/components/ui/` (`button`, `badge`, `table`, `input`, `skeleton`, `dialog`):
  - **Diretriz Vercel (`bundle-barrel-imports`):** Criar cada componente isolado sem barrel file `index.ts`.
  - **Diretriz Vercel (`rendering-conditional-render`):** Usar operadores ternários estritos em todos os renders condicionais.
- [ ] **T070**: Implementar a camada de dados em `frontend/src/lib/`:
  - `api-client.ts`: Cliente HTTP desacoplado com injeção automática de `X-Admin-Api-Key`.
  - `swr-fetcher.ts`: Fetcher tipado padrão para requisições SWR com deduplicação.
  - `types.ts`: Tipagens TypeScript estritas espelhando as entidades da WhatsApp AI Harness.
- [ ] **T071**: Implementar endpoints auxiliares na Admin API do backend (`src/harness/edge/admin_api.py`):
  - `GET /admin/threads` (listagem das conversas com última mensagem e status).
  - `GET /admin/threads/{id}/messages` (histórico de mensagens da conversa).
  - `POST /admin/queue/dlq/replay` (reprocessamento de mensagens com falha na fila).
  - `GET /admin/audit/logs` (eventos de auditoria e bloqueios de segurança).
- [ ] **T072**: Construir o Shell Global da aplicação (`frontend/src/app/layout.tsx` e `components/layout/`):
  - Provedor global `<SWRConfig>` com revalidação inteligente.
  - Sidebar fixa compacta e Header superior com indicador de pulso da Admin API (`8001`) e alternador de tema.

---

### Fase 2: Módulos Centrais de Atendimento e Fila (P1)
- [ ] **T073**: Implementar a Tela 1: **Dashboard Executivo** (`frontend/src/app/page.tsx`):
  - **Diretriz Vercel (`async-parallel` & `async-suspense-boundaries`):** Carregamento em paralelo de métricas de saúde, fila e conversas dentro de limites `<Suspense>`.
  - Blocos analíticos: Volume de Mensagens, Latência Média, Proporção Bot vs Humano e Bloqueios.
- [ ] **T074**: Implementar a Tela 2: **Conversas (Split-View em 3 Colunas)** (`frontend/src/app/conversations/page.tsx`):
  - **Coluna 1 (Lista):** Contatos recentes com `content-visibility: auto` (`rendering-content-visibility`) e busca com `useTransition` (`rerender-transitions`).
  - **Coluna 2 (Chat):** Histórico de mensagens com scroll automático, balões limpos e ação com mutação otimista via SWR: **"Assumir conversa"** (Handoff) e **"Devolver ao assistente"**.
  - **Coluna 3 (Contexto):** Painel lateral com a Memória Semântica do cliente (fatos conhecidos, preferências e resumo executivo da conversa).
  - Estados vazios orientativos e sem erros vagos conforme a diretriz de microcópia.
- [ ] **T075**: Implementar a Tela 3: **Fila de Processamento & DLQ** (`frontend/src/app/queue/page.tsx`):
  - Indicadores numéricos compactos dos 4 estados (`pending`, `processing`, `done`, `dead`).
  - Tabela operacional de alta densidade com botão de ação direta **"Reprocessar mensagem"** para itens mortos.

---

### Fase 3: Segurança, Governança e Auditoria de Performance (P2 & P3)
- [ ] **T076**: Implementar a Tela 4: **Central de Segurança & Auditoria** (`frontend/src/app/security/page.tsx`):
  - Tabela de auditoria com destaque para bloqueios de injeção de prompt e guardrails acionados.
  - Exibição de telefone com máscara e motivo do bloqueio em linguagem clara.
- [ ] **T077**: Implementar a Tela 5: **Agentes & Prompts** (`frontend/src/app/agents/page.tsx`):
  - **Diretriz Vercel (`bundle-dynamic-imports`):** Carregar o editor de YAML de Prompts dinamicamente via `next/dynamic({ ssr: false })`.
  - Controles para ligar/desligar a Pesquisa Profunda (Deep Research) e RAG.
  - Seleção de modelo e parâmetros cognitivos.
- [ ] **T078**: **Auditoria Dupla: Design & Performance (Skills `frontend-design` + `vercel-react-best-practices`)**:
  - Validar ausência de waterfalls de rede (`async-`).
  - Verificar ausência de barrel files (`bundle-barrel-imports`).
  - Validar fluidez a 60fps em buscas com `useTransition`.
  - Checar contrastes, ausência de clichês visuais de IA e conformidade com WCAG AA.
- [ ] **T079**: Testes de integração E2E do Frontend com a Admin API FastAPI e documentação completa de execução no `README.md`.
