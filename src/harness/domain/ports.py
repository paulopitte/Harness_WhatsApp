"""Ports & Interfaces de Domínio via `typing.Protocol` (SOLID ISP & DIP).

Equivalente no C#/.NET: Interfaces `IQueueEnqueuer`, `IQueueConsumer`, `IOutboundProvider`, etc.
No Python 3.13, `@runtime_checkable class ... (Protocol)` permite *Structural Subtyping*
verificado estaticamente pelo `mypy` e em tempo de execução com `isinstance()`, sem acoplar
o domínio a bibliotecas externas de infraestrutura.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from harness.domain.events import QueueStats
from harness.domain.message import NormalizedTextMessage
from harness.domain.queue import QueueItem
from harness.domain.value_objects import QueueStatus, ThreadId


@runtime_checkable
class QueueEnqueuerProtocol(Protocol):
    """Porta usada exclusivamente pela Borda (`edge/`) para enfileirar mensagens com debounce."""

    async def enqueue_with_debounce(
        self,
        message: NormalizedTextMessage,
        debounce_seconds: float,
    ) -> UUID | None:
        """Insere ou concatena mensagem pendente para a mesma `thread_id`.

        Retorna o `UUID` do `QueueItem` atualizado/criado, ou `None` caso o
        `provider_message_id` já tenha sido processado (idempotência — FR-005).
        """
        ...


@runtime_checkable
class QueueConsumerProtocol(Protocol):
    """Porta usada pelo Worker (`workers/`) e Admin (`ops/`) para consumir e gerenciar a fila."""

    async def claim_next_ready(self, worker_id: str) -> QueueItem | None:
        """Obtém lock atômico (`SKIP LOCKED`) do próximo item `pending` com `scheduled_for <= now()`."""
        ...

    async def mark_done(self, item_id: UUID) -> None:
        """Marca o item como `done` somente após confirmação de entrega do Outbound (FR-009)."""
        ...

    async def mark_failed_or_dead(
        self,
        item_id: UUID,
        error_message: str,
        backoff_seconds: float,
    ) -> QueueItem:
        """Incrementa `attempts`; se `< max_retries` reagenda como `pending`, senão move para `dead`."""
        ...

    async def reprocess_dead_items(self) -> int:
        """Re-enfileira itens `dead` para `pending` com `attempts = 0` (FR-018)."""
        ...

    async def get_stats(self) -> QueueStats:
        """Retorna estatísticas atuais da fila e quarentena."""
        ...

    async def list_items(
        self, status: QueueStatus | None = None, limit: int = 50
    ) -> list[QueueItem]:
        """Lista itens da fila opcionalmente filtrados por status."""
        ...


@runtime_checkable
class OutboundProviderProtocol(Protocol):
    """Porta agnóstica para envio de mensagens ao WhatsApp (`ConsoleMock`, `MetaCloud`, etc.)."""

    async def send_text(self, recipient_phone: str, text: str) -> bool:
        """Envia mensagem em nova conexão e retorna `True` se confirmado com sucesso."""
        ...


@runtime_checkable
class RetrieverPort(Protocol):
    """Porta agnóstica para busca vetorial RAG (`PGVector`, `Qdrant`, `InMemory` — FR-013)."""

    async def retrieve_context(self, query: str, top_k: int = 4) -> list[str]:
        """Recupera os trechos relevantes da base de conhecimento institucional."""
        ...


@runtime_checkable
class PromptProviderPort(Protocol):
    """Porta agnóstica para PromptOps no Langfuse com fallback YAML local (FR-021)."""

    async def get_system_prompt(
        self,
        prompt_name: str,
        label: str = "production",
        variables: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Retorna a tupla `(compiled_prompt_text, version_identifier)`."""
        ...


@runtime_checkable
class CognitionEngineProtocol(Protocol):
    """Fachada única exportada por `cognition/` para o pipeline do worker."""

    async def generate_reply(
        self,
        thread_id: ThreadId,
        user_text: str,
        queue_item_id: UUID | None = None,
    ) -> str:
        """Executa o motor de cognição (`EchoAgent` ou `LangGraph` com Guardrails, Middlewares e RAG)."""
        ...


# Aliases para compatibilidade de nomenclatura Port / Protocol
RetrieverProtocol = RetrieverPort
PromptProviderProtocol = PromptProviderPort


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    """Resultado individual de busca na web."""

    title: str
    snippet: str
    link: str
    source_name: str = ""


@runtime_checkable
class WebSearchPort(Protocol):
    """Porta agnóstica para pesquisa profunda na Web (DuckDuckGo, Tavily, Google Search)."""

    @property
    def provider_name(self) -> str: ...

    async def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        """Executa busca assíncrona na Web e retorna lista de resultados estruturados."""
        ...


@dataclass(frozen=True, slots=True)
class CrawledPage:
    """Página ou produto extraído de um site corporativo."""

    url: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class WebsiteCrawlerPort(Protocol):
    """Porta para extração e rastreamento de páginas/produtos de qualquer site corporativo."""

    async def crawl_site(self, base_url: str, max_pages: int = 50) -> list[CrawledPage]:
        """Rastreia assincronamente a URL base e retorna páginas extraídas com conteúdo limpo."""
        ...

