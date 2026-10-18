# Repository review changes
_Exported on 10/16/2026 at 17:59:49 GMT-3 from Cursor (3.25.6)_

---

**User**

/review-bugbot Review changes in the repository at "d:\\CURSOS\\LANGCHAIN\\PauloPItte\\exemplos_langchainV1LangGraph".

Nesse vídeo https://youtu.be/uezD0dRdz9Q?is=mx6l_ZYnA7pw8ZaX
Analise a arquitetura competa apresentada e monte um projeto modelo/template em python, por enquanto nao escreva codigo agora, só me oriente na estrutura do projetos seguindo esse harness, 

---

**Cursor**

Vou analisar o vídeo e o repositório para montar a estrutura do projeto no estilo do harness, sem escrever código ainda.

O vídeo do Hulk não ensina “um agente”. Ele ensina um **sistema de produção**: a LLM fica no miolo; a **harness** é tudo o que a LLM não faz bem (receber, validar, enfileirar, memória, retry, observabilidade, envio).

Abaixo está a arquitetura do vídeo, traduzida em **estrutura de projeto Python**, alinhada ao que você já usa neste repo (`create_agent`, LangGraph, middleware, runtime). Sem código, só o mapa.

## O que é harness neste vídeo

| É harness | Não é harness |
|---|---|
| Scaffolding em volta do modelo: borda, fila, worker, contexto, memória, persistência, outbound, operação | Só chamar API |
| Fronteiras de responsabilidade pensadas desde o início | Um app com um agente no mesmo processo da borda |
| Runtime: guardar, recuperar, controlar, retry, telemetria | Um único script `agente.py` |

No WhatsApp o desafio extra é: **não existe “nova thread”**. A identidade da conversa é o telefone (ou hash). Por isso thread, debounce, sumarização e memória semântica entram na arquitetura, não “depois”.

## Fluxo ponta a ponta

```text
Usuário (WhatsApp)
    → Provedor (Meta / outro)          [canal isolado]
    → Borda: webhook ACK imediato
    → validar → rate limit → normalizar
    → texto? debounce  |  mídia? áudio/imagem → texto  |  vídeo? recusa
    → Fila (Postgres)
    → Worker(s) N
    → Cognição (grafo LangChain/LangGraph/Deep Agents)
         + sumarização automática
         + memória semântica (fatos do usuário)
    → Outbound (nova conexão para o provedor)
    → confirma envio → marca fila DONE
    → falha → reenqueue (ex.: 3 tentativas) → DEAD
```

Regra de ouro do vídeo: **a fila só recebe texto já pré-processado**. O agente não precisa ser multimodal. Troca de modelo/framework fica barata.

## Camadas → pastas

Monte o template como um **pacote**, não como exemplos soltos. Algo neste formato:

```text
whatsapp_harness/
├── pyproject.toml
├── README.md
├── .env.example
├── configs/
│   └── harness.yaml                 # debounce, retries, mídia on/off, modelo
│
├── src/harness/
│   ├── __init__.py
│   ├── settings.py                  # env + yaml
│   │
│   ├── domain/                      # contratos internos (sem WhatsApp, sem LLM)
│   │   ├── message.py               # InboundMessage, NormalizedTextMessage
│   │   ├── thread.py                # thread_id = phone/hash
│   │   ├── queue.py                 # QueueItem, status: pending|processing|done|dead
│   │   └── events.py                # telemetria: received, queued, failed...
│   │
│   ├── edge/                        # BORDA — receber bem e ACK rápido
│   │   ├── webhook.py               # HTTP: recebe, ACK Meta, devolve 200
│   │   ├── verify.py                # payload válido / assinatura
│   │   ├── rate_limit.py            # anti-loop agente↔agente e abuso de custo
│   │   ├── normalize.py             # lixo fora, schema único
│   │   ├── debounce.py              # "oi" + enter + "tudo bem" → 1 item
│   │   └── media/                   # fronteira: mídia vira texto ANTES da fila
│   │       ├── router.py            # texto | áudio | imagem | vídeo
│   │       ├── transcribe.py
│   │       └── vision_to_text.py
│   │
│   ├── ingress/                     # INGESTÃO
│   │   ├── enqueue.py
│   │   └── postgres_queue.py        # fila manual (trocável por Redis/Rabbit)
│   │
│   ├── workers/                     # PROCESSAMENTO — escala horizontal
│   │   ├── runner.py                # N workers puxam a fila
│   │   ├── claim.py                 # lock/claim atômico
│   │   └── pipeline.py              # limpa → chama cognição → outbound → ack
│   │
│   ├── cognition/                   # INTELIGÊNCIA — único lugar que fala com LLM
│   │   ├── graph.py                 # exporta grafo (create_agent | StateGraph | deep agents)
│   │   ├── agents/                  # N agentes plugáveis (painel lista todos)
│   │   │   └── default_agent.py
│   │   ├── context.py               # compactação/sumarização (estilo Claude Code)
│   │   ├── semantic_memory.py       # fatos do usuário (ex.: "gosta de chocolate")
│   │   └── thread_store.py          # histórico da thread WhatsApp
│   │
│   ├── outbound/                    # ENVIO — nova conexão, sem streaming
│   │   ├── sender.py
│   │   ├── providers/
│   │   │   ├── meta.py
│   │   │   └── protocol.py          # interface: send(text) → ok/fail
│   │   └── retry.py                 # 3 tentativas → dead
│   │
│   ├── persistence/                 # histórico operacional (painel)
│   │   ├── conversations.py
│   │   └── runs.py
│   │
│   ├── ops/                         # OPERAÇÃO
│   │   ├── observability.py         # fila, erros, telemetria
│   │   ├── admin_api.py             # conversas, agentes, fila, usuários
│   │   └── security.py              # usuários/admin
│   │
│   └── app.py                       # composição (wiring), sem lógica de negócio
│
├── tests/
│   ├── test_edge_verify.py
│   ├── test_debounce.py
│   ├── test_queue_claim.py
│   ├── test_retry_dead.py
│   └── load/                        # teste de carga do próprio vídeo
│
└── scripts/
    ├── run_webhook.py
    ├── run_worker.py
    └── run_admin.py
```

Três processos distintos (como no vídeo: borda fraca vs agente pesado):

1. **webhook** — ACK rápido, valida, debounce, enfileira  
2. **worker** — puxa fila, chama grafo, envia, marca done/dead  
3. **admin** — observabilidade, conversas, fila, segurança  

Não coloque LLM no mesmo request do webhook. Foi exatamente o anti-padrão que ele descreveu (pico → CPU saturada → mensagem perdida em silêncio).

## Fronteiras que o template deve preservar

1. **Canal ≠ borda ≠ inteligência**  
   Trocar Meta por outro provedor não mexe no agente. Trocar LangGraph por Deep Agents não mexe no webhook.

2. **Contrato da fila = texto + thread_id + metadata**  
   Áudio/imagem morrem na borda. Vídeo: resposta fixa “formato não suportado”, sem LLM.

3. **Thread é identidade, não “chat session” de UI**  
   `thread_id` nasce do telefone. Checkpointer/memória usam isso. Não invente “nova conversa” no WhatsApp sem regra explícita.

4. **Dois tipos de memória**  
   - **Operacional/contexto:** histórico + sumarização (pode perder detalhe).  
   - **Semântica:** fatos estáveis do usuário, persistidos à parte.

5. **Fila é componente, não dogma**  
   Comece com Postgres (como no vídeo: ensina o ciclo pending → processing → done/dead). Deixe `postgres_queue.py` atrás de uma interface para um dia ir a Redis/PGMQ.

6. **Outbound é outra conexão**  
   WhatsApp não é streaming de tokens. Recebe, fecha, processa, abre envio, confirma, só então `DONE`.

7. **Cognição exporta grafo**  
   `cognition/graph.py` deve ser o único ponto que o worker chama. Assim você pluga o que já tem neste curso: `create_agent`, middleware de summarization, HITL, runtime context.

## Como isso conversa com o seu repo atual

O que você já tem é a **camada verde do diagrama** (o agente), não a harness:

| Pasta atual | Onde entra no template |
|---|---|
| `exemplo_chatmodels` | modelo dentro de `cognition/` |
| `exemplo_agente_simples` | `cognition/agents/default_agent.py` |
| `exemplo_middleware` | hooks de contexto/sumarização |
| `exemplo_runtime` | `Runtime[Context]` no grafo (thread, user facts) |
| `agente_pesquisa.py` | um agente plugável + SummarizationMiddleware |

O template novo deve **envolver** isso, não misturar webhook/fila dentro desses exemplos.

## Stack sugerida (fiel ao vídeo + ao curso)

- Python 3.13 + `uv` (já é o padrão do repo)
- HTTP: FastAPI só na borda e no admin
- Fila + persistência: Postgres (uma base, várias tabelas: `queue`, `threads`, `semantic_facts`, `runs`)
- Cognição: LangChain v1 / LangGraph (grafo compilado)
- Config: YAML + env (mídia on/off, debounce ms, max retries, modelo barato vs caro)
- Observabilidade: eventos na mesma base no início; LangSmith depois, se quiser

Não comece com Rabbit, cluster, multimodal no agente, streaming, nem “sistema operacional genérico”. O vídeo é explícito: harness de **um problema** (agente WhatsApp), modelo commodity, arquitetura pronta para crescer.

## Ordem de implementação (quando for para código)

1. `domain` + `edge` (webhook ACK + validate)  
2. fila Postgres + status visíveis  
3. worker que só ecoa texto (sem LLM)  
4. outbound + retry/dead  
5. plugar `create_agent`  
6. debounce + mídia→texto  
7. sumarização + memória semântica  
8. admin (fila, conversas, erros)  
9. load test para dimensionar workers  

Se pular 1–4 e começar pelo agente, você volta a ter “app com agente”, não harness.

Quando quiser, no Agent mode dá para materializar esse esqueleto (pastas, contratos, `harness.yaml`) sem ainda ligar Meta nem LLM.

