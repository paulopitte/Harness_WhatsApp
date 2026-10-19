"""Motor de Cognição `EchoAgent` para Validação Local a Custo Zero (FR-010).

Implementa `CognitionEngineProtocol` (Liskov Substitution Principle — SOLID):
o pipeline do worker chama `generate_reply()` sem saber se por trás está o `EchoCognitionEngine`
ou o grafo completo do `LangGraphCognitionEngine`.
"""

from uuid import UUID

from harness.domain.value_objects import ThreadId


class EchoCognitionEngine:
    """Agente determinístico que ecoa o texto consolidado (pós-debounce) recebido na fila."""

    async def generate_reply(
        self,
        thread_id: ThreadId,
        user_text: str,
        queue_item_id: UUID | None = None,
    ) -> str:
        """Retorna uma mensagem formatada comprovando o agrupamento de debounce e a thread."""
        lines = [line.strip() for line in user_text.splitlines() if line.strip()]
        joined = " | ".join(lines)
        return f"[EchoAgent | {thread_id.value}] Recebi ({len(lines)} msg): {joined}"

