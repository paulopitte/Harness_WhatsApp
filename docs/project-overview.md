# Visão Geral do Produto (Project Overview)

> **Última atualização:** 2026-10-26  
> **Status:** Em produção / Estável  
> **Documentação de Arquitetura:** [docs/architecture.md](./architecture.md) | **Guia de Onboarding:** [README.md](../README.md)

---

## 1. O Que É o WhatsApp AI Harness?

O **WhatsApp AI Harness** é uma infraestrutura corporativa de software desacoplada, orientada a eventos e baseada no padrão **Ports & Adapters (Hexagonal)**, projetada especificamente para operar agentes inteligentes no WhatsApp em escala industrial.

Diferente de scripts convencionais ou wrappers de LLM que colocam a inteligência artificial diretamente nas rotas HTTP de webhook, o Harness atua como uma camada operacional e de governança (_Harness Engineering_). O sistema trata o modelo de linguagem (LLM) como uma commodity intercambiável, externalizando memória, ferramentas, filas transacionais e observabilidade.

---

## 2. Dores Reais do Mercado que o Produto Resolve

Mais de 90% dos bots de IA para WhatsApp falham ao sair de testes e entrar em produção real devido a quatro gargalos críticos:

1. **Gargalo no Webhook & Loops da Meta:** A Meta Cloud API exige resposta HTTP (`200 OK`) em menos de 2 a 3 segundos. Se a chamada da LLM levar 5 a 15 segundos na mesma requisição, a Meta assume timeout e reenvia a mensagem, gerando loops de execução duplicada e custos imprevistos de tokens.
2. **Rajadas de Mensagens sem Debounce:** Usuários do WhatsApp costumam fracionar pensamentos em várias mensagens curtas seguidas (_"Olá"_, _"Tudo bem?"_, _"Quanto custa o serviço?"_). Sem debounce persistido, o sistema dispara múltiplas execuções concorrentes e desordenadas para o mesmo usuário.
3. **Explosão de Contexto e Custo:** Conversas no WhatsApp não têm botão de "Novo Chat" e podem durar semanas ou meses. Sem auto-sumarização e segregação de memória semântica, o histórico satura a janela de contexto da LLM e estoura os limites de custos diários.
4. **Acoplamento Extremo (Vendor Lock-in):** A mistura de SDKs de mensageria com lógica de agentes e chamadas diretas de banco impede trocas rápidas de provedor de IA ou de canais de saída.

---

## 3. Capacidades Principais do Sistema

- **Ingestão Assíncrona com ACK Instantâneo (`< 150ms`):** A camada de borda valida a autenticidade da requisição via HMAC (`X-Hub-Signature-256`), sanitiza dados, normaliza mídias (áudio/imagem) para texto e retorna `200 OK` imediatamente.
- **Debounce e Deduplicação Persistidos no PostgreSQL:** O agrupamento de mensagens consecutivas é gerenciado no banco através de agendamento transacional (`scheduled_for`) e índice parcial exclusivo para mensagens pendentes, evitando concorrência em memória.
- **Workers Assíncronos com Concorrência Segura:** Consumo contínuo da fila com `SELECT ... FOR UPDATE SKIP LOCKED`, garantindo que múltiplos processos ou nós nunca processem a mesma conversa simultaneamente.
- **Dupla Camada de Memória:**
  - _Memória Operacional:_ Histórico recente da conversa com sumarização automática após ultrapassar o teto configurado de mensagens.
  - _Memória Semântica:_ Armazenamento persistente de fatos declarados pelo cliente (nome, preferências, regras de negócio) reutilizados em sessões futuras.
- **Transbordo Humano (_Handoff_):** Alternância transparente do modo da thread entre `bot`, `human` e `paused`. No modo humano, o agente silencia suas respostas e as mensagens são encaminhadas aos atendentes.
- **Pesquisa Profunda na Web (_Deep Research_):** Agente de pesquisa analítica em 4 estágios (planejamento de busca, execução de consultas, extração de conteúdo e síntese com citação de fontes confiáveis).
- **Ingestão de Catálogos e Sites Corporativos:** Crawler embutido para indexação de websites e leitura de documentos PDF na base de conhecimento vetorial (`pgvector`).
- **PromptOps Dinâmico com Zero-Downtime:** Versionamento e gestão de prompts via Langfuse (labels `production`, `staging`, `canary`) com fallback automático para arquivos locais YAML sem necessidade de redeploy.
- **Resiliência com Dual DLQ:** Isolamento de falhas de transporte na Quarentena de Borda (_Edge DLQ_) e de falhas cognitivas ou externas na Fila de Mensagens Mortas de Negócio (_Business DLQ_).
- **Interfaces de Operação e Teste:**
  - _Admin & Operations API:_ Endpoints REST para métricas, inspeção de threads, fatos semânticos e reprocessamento de DLQ.
  - _Cockpit SaaS (Next.js 16 + React 19):_ Painel com inbox ao vivo, monitoramento de saúde, fila em tempo real e auditoria de segurança.
  - _Chainlit UI:_ Interface web conversacional para testes rápidos e demonstração ao vivo.

---

## 4. Perfis de Usuários e Casos de Uso

| Papel                        | Interação com o Sistema                                                    | Benefício Principal                                                                          |
| :--------------------------- | :------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------- |
| **Cliente Final (WhatsApp)** | Envia mensagens de texto, áudio e fotos pelo WhatsApp.                     | Respostas rápidas, contextuais e suporte contínuo sem repetição de informações.              |
| **Atendente Humano**         | Assume conversas via Cockpit (`/conversations`) e atua em casos complexos. | Transbordo suave sem perda do histórico ou dos fatos do cliente.                             |
| **Operador / Gestor**        | Monitora DLQ, custos de tokens, taxa de bloqueios e métricas gerais.       | Visibilidade operacional ponta a ponta e recuperação com 1 clique de falhas.                 |
| **Engenheiro de Software**   | Desenvolve novas ferramentas, conecta novos canais ou modelos de IA.       | Arquitetura desacoplada via `typing.Protocol`, com testes unitários e de integração sólidos. |

---

## 5. Próximos Passos e Referências

- Para entender detalhes das camadas, fluxo de dados, contratos e modelo do PostgreSQL, consulte [docs/architecture.md](./architecture.md).
- Para subir os serviços localmente passo a passo, consulte o guia de início em [README.md](../README.md).
