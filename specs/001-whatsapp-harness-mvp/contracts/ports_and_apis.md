# Phase 1: Architecture Ports & API Contracts (`contracts/ports_and_apis.md`)

**Feature**: `001-whatsapp-harness-mvp`  
**Date**: 2026-10-19  
**Spec**: [spec.md](../spec.md)

Este documento especifica os **Contratos Internos (`typing.Protocol` — Interfaces estilo C#)** da camada `domain/ports.py` e os **Contratos HTTP Externos** (`edge/` e `ops/`).

---

## 1. Ports & Interfaces de Domínio (`src/harness/domain/ports.py`)

Seguindo o **Interface Segregation Principle (ISP)** e **Dependency Inversion Principle (DIP)** do SOLID:

```python
from typing import Protocol, runtime_checkable
from uuid import UUID
from harness.domain.message import NormalizedTextMessage
from harness.domain.queue import QueueItem
from harness.domain.thread import ThreadId, ThreadMode


@runtime_checkable
class QueueEnqueuerProtocol(Protocol):
    """Porta usada exclusivamente pela Borda (edge/) para enfileirar mensagens com debounce."""

    async def enqueue_with_debounce(
        self,
        message: NormalizedTextMessage,
        debounce_seconds: float,
    ) -> UUID | None:
        """
        Insere ou concatena mensagem pendente para a mesma thread_id.
        Retorna None caso provider_message_id já tenha sido processado (idempotência).
        """
        ...


@runtime_checkable
class QueueConsumerProtocol(Protocol):
    """Porta usada exclusivamente pelo Worker (workers/) para consumir e atualizar a fila."""

    async def claim_next_ready(self, worker_id: str) -> QueueItem | None:
        """Obtém lock exclusivo (SKIP LOCKED) do próximo item com scheduled_for <= now()."""
        ...

    async def mark_done(self, item_id: UUID) -> None:
        """Marca o item como 'done' após confirmação do provedor outbound."""
        ...

    async def mark_failed_or_dead(
        self,
        item_id: UUID,
        error_message: str,
        backoff_seconds: float,
    ) -> None:
        """Incrementa attempts; se < max_retries reagenda como 'pending', senão marca 'dead'."""
        ...


@runtime_checkable
class OutboundProviderProtocol(Protocol):
    """Porta agnóstica para envio de mensagens ao WhatsApp (ConsoleMock, MetaCloud, Evolution)."""

    async def send_text(self, recipient_phone: str, text: str) -> bool:
        """Envia mensagem em nova conexão HTTP e retorna True se confirmado com sucesso."""
        ...


@runtime_checkable
class RetrieverPort(Protocol):
    """Porta agnóstica para busca vetorial RAG (PGVector, Qdrant, InMemory)."""

    async def retrieve_context(self, query: str, top_k: int = 4) -> list[str]:
        """Retorna os trechos de documentos mais relevantes por similaridade semântica."""
        ...


@runtime_checkable
class PromptProviderPort(Protocol):
    """Porta agnóstica para gerenciamento e versionamento de prompts (Langfuse + YAML Fallback)."""

    async def get_system_prompt(
        self,
        prompt_name: str,
        label: str = "production",
        variables: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Retorna (compiled_prompt_text, version_identifier)."""
        ...


@runtime_checkable
class CognitionEngineProtocol(Protocol):
    """Fachada única exportada por cognition/ para o pipeline do worker."""

    async def generate_reply(
        self,
        thread_id: ThreadId,
        user_text: str,
    ) -> str:
        """Executa o grafo (EchoAgent ou LangGraph com Guardrails, Middlewares, Memória e RAG)."""
        ...
```

---

## 2. Contratos HTTP da Borda (`src/harness/edge/webhook.py`)

### 2.1. `GET /webhook` (Verificação de Desafio da Meta)
- **Query Params**: `hub.mode=subscribe`, `hub.verify_token=<token>`, `hub.challenge=<string>`
- **Respostas**:
  - `200 OK`: Retorna o valor de `hub.challenge` em texto puro se `verify_token` coincidir.
  - `403 Forbidden`: RFC 9457 `ProblemDetails` em português caso o token seja inválido.

### 2.2. `POST /webhook` (Ingestão de Eventos WhatsApp)
- **Headers**:
  - `X-Hub-Signature-256`: `sha256=<hmac_hex>` (obrigatório quando `security.verify_signature=true`).
- **Payload de Entrada (Compatível com Meta Cloud API / Simulador Local)**:
```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "WABA_ID",
      "changes": [
        {
          "field": "messages",
          "value": {
            "contacts": [{ "wa_id": "5511999998888", "profile": { "name": "Paulo" } }],
            "messages": [
              {
                "id": "wamid.HBgNNTUxMTk5OTk5ODg4OBUCABIYFDNB",
                "from": "5511999998888",
                "timestamp": "1760870000",
                "type": "text",
                "text": { "body": "Olá, gostaria de saber sobre a política de reembolso" }
              }
            ]
          }
        }
      ]
    }
  ]
}
```
- **Respostas**:
  - `200 OK` (`< 150ms`): `{"status": "accepted", "disposition": "queued | deduplicated | quarantined | rate_limited"}`
  - `503 Service Unavailable`: Apenas quando o banco de dados estiver inacessível após as 3 tentativas do Fast-Retry (`tenacity`).

---

## 3. Contratos HTTP da API Administrativa (`src/harness/ops/admin_api.py`)

Protegidos por cabeçalho `X-Admin-Api-Key`:

| Método e Rota | Descrição | Retorno (`200 OK`) |
| :--- | :--- | :--- |
| `GET /admin/queue/stats` | Contagem de itens por estado (`pending`, `processing`, `done`, `dead`) e quarentena (`quarantine_inbound`). | `QueueStatsResponse` |
| `POST /admin/queue/reprocess-dead` | Re-enfileira itens `dead` para `pending` com `attempts = 0` e `scheduled_for = now()`. | `{"requeued_count": int}` |
| `PATCH /admin/threads/{thread_id}/mode` | Altera o modo da thread entre `"bot"`, `"human"` (Handoff) e `"paused"`. | `{"thread_id": str, "mode": str}` |
| `GET /admin/threads/{thread_id}/facts` | Lista os fatos semânticos aprendidos e o sumário atual da conversa. | `ThreadMemoryResponse` |

