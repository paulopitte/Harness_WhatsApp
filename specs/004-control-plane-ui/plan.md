# Plano Arquitetural & Performance: Painel de Controle Empresarial (004-control-plane-ui)

> **SpecKit — Technical Design, Visual Architecture & Vercel Best Practices**  
> *Diretório alvo do Frontend: `frontend/`*  
> *Padrões de Interface: Alinhados com a skill `frontend-design`.*  
> *Padrões de Performance: Alinhados com a skill `vercel-react-best-practices`.*

---

## 🎨 1. Sistema de Tokens Visuais & Identidade

Em conformidade com a skill `frontend-design`, evitamos deliberadamente os clichês estéticos de interfaces geradas por IA (paletas bege/terracota, grids infinitos de cards flutuantes idênticos, rótulos decorativos em CAIXA ALTA e gradientes roxos sem função).

### 🌈 1.1 Paleta de Cores Estrutural (Tokens Nomeados)

```css
:root {
  /* Canvas e Fundos Estruturais */
  --bg-canvas: #0b0f19;        /* Ardósia profunda, quase obsidian, sem preto artificial */
  --bg-surface: #111827;       /* Superfície dos painéis e blocos de conteúdo */
  --bg-surface-hover: #1f2937; /* Estado de hover de linhas de tabela e itens de lista */
  
  /* Bordas e Delimitações Estruturais */
  --border-subtle: #1f2937;    /* Divisões de alta precisão entre painéis */
  --border-strong: #374151;    /* Bordas de foco e elementos interativos */

  /* Cores Semânticas de Estado */
  --status-active: #10b981;    /* Verde esmeralda: bot ativo, conexão online, fila saudável */
  --status-attention: #f59e0b; /* Âmbar: atendimento humano assumido, retries em andamento */
  --status-critical: #f43f5e;  /* Carmim: mensagem morta (DLQ), ataque de injeção bloqueado */
  
  /* Tipografia */
  --text-primary: #f8fafc;     /* Leitura primária de alta legibilidade */
  --text-muted: #94a3b8;       /* Metadados, datas, descrições secundárias */
}
```

### 🔤 1.2 Tipografia e Hierarquia

* **Família Primária:** `Geist Sans` ou `Inter` (Sans-serif moderno, geométrico e neutro).
  - Títulos: Peso 600 (Semibold), rastreamento ligeiramente fechado (`-0.02em`), em **Sentence case** (nunca caixa alta).
  - Corpo: Peso 400 (Regular), entrelinha generosa (`leading-relaxed`), limitado a **75 caracteres por linha**.
* **Família Técnica:** `Geist Mono` ou `JetBrains Mono` (Monoespaçado).
  - Usado exclusivamente para: Números de telefone E.164 (`+55 11 99999-8888`), IDs de mensagem, timestamps ISO, contadores de fila e trechos de código/JSON.

---

## ⚡ 2. Arquitetura de Performance Vercel (`vercel-react-best-practices`)

Para garantir máxima velocidade de carregamento e tempo de resposta instantâneo, o frontend adota os padrões prioritários da Vercel:

### 2.1 Eliminação de Waterfalls (`async-`)
* **Paralelismo com SWR e `Promise.all` (`async-parallel`):** O Dashboard carrega as métricas de saúde, fila e conversas em paralelo, eliminando bloqueios em cascata.
* **Limites com `<Suspense>` (`async-suspense-boundaries`):** Cada coluna do Split-View de Atendimento (Lista, Chat e Perfil Semântico) é envolvida em seu próprio `<Suspense fallback={<Skeleton />}>`, permitindo que o shell da página renderize instantaneamente enquanto os dados chegam por streaming.

### 2.2 Otimização do Tamanho de Pacote / Bundle (`bundle-`)
* **Proibição Estrita de Barrel Files (`bundle-barrel-imports`):**
  ```typescript
  // ❌ Incorreto (importação via barrel puxa componentes não utilizados)
  import { Button, Input, Card } from "@/components/ui";

  // ✅ Correto (importação direta por módulo)
  import { Button } from "@/components/ui/button";
  import { Input } from "@/components/ui/input";
  import { Card } from "@/components/ui/card";
  ```
* **Carregamento Dinâmico de Componentes Pesados (`bundle-dynamic-imports`):** O editor de YAML de Prompts da rota `/agents` utiliza `next/dynamic` com `{ ssr: false }`, poupando o bundle inicial do cliente:
  ```typescript
  import dynamic from "next/dynamic";
  const YamlEditor = dynamic(() => import("@/components/agents/yaml-editor"), {
    ssr: false,
    loading: () => <Skeleton className="h-96 w-full" />
  });
  ```

### 2.3 Camada de Dados com SWR e Mutações Otimistas (`client-swr-dedup`)
* A biblioteca **SWR** é utilizada em todas as chamadas à Admin API (`http://localhost:8001`), oferecendo:
  - Deduplicação automática de requisições simultâneas.
  - Revalidação em segundo plano sem travar a interface (`stale-while-revalidate`).
  - Mutações otimistas instantâneas no Handoff Humano (o botão de assumir atendimento alterna o status no cliente antes mesmo de receber a resposta HTTP da porta 8001).

### 2.4 Prevenção de Re-renderizações Desnecessárias (`rerender-`)
* **Estado Derivado Calculado no Render (`rerender-derived-state-no-effect`):** A filtragem de conversas por telefone ou modo é calculada inline na renderização com `useMemo` simples, nunca via `useEffect` + `setState`.
* **Transições Não-Urgentes (`rerender-transitions`):** O campo de busca de contatos utiliza `useTransition` para que a digitação do operador permaneça a 60fps enquanto a filtragem da lista é processada em segundo plano.
* **Proibição de Sub-componentes Inline (`rerender-no-inline-components`):** Todos os itens de lista, balões de chat e linhas de tabela são componentes declarados no escopo do módulo.

### 2.5 Eficiência de Renderização no DOM (`rendering-`)
* **Renderização Condicional Ternária (`rendering-conditional-render`):**
  ```tsx
  // ❌ Incorreto (pode renderizar 0 no DOM)
  {items.length && <Badge>{items.length}</Badge>}

  // ✅ Correto
  {items.length > 0 ? <Badge>{items.length}</Badge> : null}
  ```
* **Virtualização e `content-visibility: auto` (`rendering-content-visibility`):** Aplicado na lista de contatos do WhatsApp para que navegadores processem rapidamente centenas de conversas sem queda de frames.

---

## 📐 3. Wireframes Estruturais (ASCII) & Layouts

### 3.1 Rota Conversas: Split-View Operacional de 3 Colunas
```
+-------------------+------------------------------------+-------------------+
|  Conversas (320px)|         Chat Ao Vivo (Flex)        | Fatos Cliente(340)|
+-------------------+------------------------------------+-------------------+
| [Q Buscar número] | [+55 11 99999-8888] [Assumir (Handoff)] | Perfil Semântico  |
|                   | Status: Assistente de IA ativo     | Nome: Paulo       |
+-------------------+------------------------------------+ Empresa: ACME     |
| * 11 99999-8888   | [Cliente - 14:32]                  | Prefere: Manhã    |
|   "Olá, gostaria" | Olá, gostaria de saber os planos   +-------------------+
|   [Bot Ativo]     |                                    | Resumo da Thread  |
|                   | [Assistente - 14:32]               | Cliente em busca  |
|   11 98888-7777   | Olá Paulo! Nossos planos começam   | do plano Pro com  |
|   "Preciso de aj" | a partir de R$ 99/mês...           | suporte dedicado. |
|   [Humano]        +------------------------------------+-------------------+
|                   | [ Digite para responder ao cliente... ] [Enviar]       |
+-------------------+--------------------------------------------------------+
```

### 3.2 Rota Fila & DLQ: Tabela de Alta Densidade com Ação Imediata
```
+----------------------------------------------------------------------------+
| Fila de Processamento & DLQ                                                |
| [ 12 Aguardando Debounce ]  [ 2 Processando ]  [ 1.420 Concluídas ]  [ 3 Mortas (DLQ) ] |
+----------------------------------------------------------------------------+
| ID Mensagem     Telefone          Status    Tentativas  Data       Ação    |
+----------------------------------------------------------------------------+
| msg_98fa21...   +55 11 9999-8888  dead      3 / 3       14:28:10   [Reprocessar] |
| msg_11bc43...   +55 11 9888-7777  dead      3 / 3       14:15:02   [Reprocessar] |
| msg_76de90...   +55 21 9777-6666  pending   0 / 3       14:30:45   -       |
+----------------------------------------------------------------------------+
```

---

## 🏛️ 4. Estrutura Modular de Arquivos (`frontend/`)

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx             # Shell global com SWRConfig Provider e Tema
│   │   ├── page.tsx               # Rota 1: Dashboard Analítico (com Suspense)
│   │   ├── conversations/         # Rota 2: Split-View 3 Colunas (Chat & Handoff)
│   │   │   └── page.tsx
│   │   ├── queue/                 # Rota 3: Fila de Processamento & Replay DLQ
│   │   │   └── page.tsx
│   │   ├── security/              # Rota 4: Central de Segurança & Guardrails
│   │   │   └── page.tsx
│   │   └── agents/                # Rota 5: Agentes, Modelos e Prompts
│   │       └── page.tsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── app-sidebar.tsx    # Navegação lateral com ícones Lucide
│   │   │   └── app-header.tsx     # Status da conexão com a porta 8001 e Dark Mode
│   │   ├── conversations/
│   │   │   ├── thread-list.tsx    # Lista de conversas com filtro via useTransition
│   │   │   ├── chat-viewport.tsx  # Histórico com scroll automático e balões nítidos
│   │   │   ├── chat-composer.tsx  # Campo de resposta do operador humano
│   │   │   └── customer-panel.tsx # Painel lateral com a Memória Semântica
│   │   ├── queue/
│   │   │   ├── queue-metrics.tsx  # Contadores rápidos (pending, processing, done, dead)
│   │   │   └── queue-table.tsx    # Tabela com ação de replay transacional
│   │   ├── security/
│   │   │   └── audit-log.tsx      # Tabela de eventos bloqueados e auditoria
│   │   └── ui/                    # Componentes atômicos sem barrel files
│   │       ├── button.tsx
│   │       ├── badge.tsx
│   │       ├── input.tsx
│   │       ├── table.tsx
│   │       └── dialog.tsx
│   ├── lib/
│   │   ├── api-client.ts          # Cliente HTTP desacoplado com injeção de X-Admin-Api-Key
│   │   ├── swr-fetcher.ts         # Fetcher padrão tipado para o SWR
│   │   ├── types.ts               # Tipagens estritas das entidades do sistema
│   │   └── utils.ts               # Formatadores de telefone, data relativa e classes
│   └── hooks/
│       ├── use-threads.ts         # Hook SWR com revalidação automática de conversas
│       └── use-queue.ts           # Hook SWR de monitoramento contínuo da fila
├── .env.example                   # NEXT_PUBLIC_ADMIN_API_URL=http://localhost:8001
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

---

## 🔍 5. Matriz de Conformidade Vercel Best Practices

| Regra Vercel | Como foi aplicada neste projeto | Benefício Prático |
| :--- | :--- | :--- |
| `async-suspense-boundaries` | Cada painel do Split-View tem seu próprio fallback de Skeleton. | O shell abre em milissegundos sem telas brancas. |
| `bundle-barrel-imports` | Proibido `index.ts` reexportando todos os componentes de UI. | Redução drástica do JavaScript transferido no primeiro carregamento. |
| `bundle-dynamic-imports` | Editor de YAML de prompts carregado com `next/dynamic({ ssr: false })`. | Mantém o código do editor Monaco/Code fora das telas comuns. |
| `client-swr-dedup` | Biblioteca `swr` gerenciando o cache e mutações otimistas. | Elimina requisições duplicadas e atualiza o handoff instantaneamente. |
| `rerender-transitions` | `useTransition` no campo de busca de contatos. | A digitação do atendente nunca trava mesmo com muitas conversas. |
| `rendering-conditional-render` | Operadores ternários estritos em todos os componentes JSX. | Impede que o número `0` vaze na interface em contadores vazios. |
