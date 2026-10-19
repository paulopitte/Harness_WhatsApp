"""Conversor de Imagem para Descrição Textual na Borda (`edge/media/vision.py` — FR-016, T041).

Regra de Ouro da Harness (Princípio III da Constitution):
Imagens enviadas pelo cliente (ex.: comprovantes, fotos de produtos ou telas de erro) são descritas
textualmente na borda ANTES do enqueue, mantendo o agente de cognição 100% focado em texto.
"""

from typing import Protocol, runtime_checkable

from harness.domain.message import InboundMediaAttachment


@runtime_checkable
class ImageVisionDescriberProtocol(Protocol):
    """Porta de descrição visual de imagem na borda."""

    async def describe(self, attachment: InboundMediaAttachment) -> str: ...


class ImageVisionDescriber:
    """Descritor de imagem na borda (com fallback determinístico local quando offline/simulador)."""

    def __init__(self, *, api_key: str = "", model_name: str = "gemini-2.5-flash") -> None:
        cleaned_key = api_key.strip()
        self._api_key = "" if cleaned_key.startswith("your_") else cleaned_key
        self._model_name = model_name

    async def describe(self, attachment: InboundMediaAttachment) -> str:
        """Converte o anexo de imagem e sua legenda opcional em descrição textual."""
        caption_part = f" (Legenda do cliente: {attachment.caption.strip()})" if attachment.caption else ""

        if attachment.raw_bytes_b64 and self._api_key:
            from langchain_core.messages import HumanMessage
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=self._model_name,
                google_api_key=self._api_key,
                temperature=0.1,
            )
            msg = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "Descreva objetivamente o conteúdo desta imagem enviada no atendimento "
                            "de WhatsApp (incluindo textos ou valores visíveis)."
                        ),
                    },
                    {
                        "type": "media",
                        "mime_type": attachment.mime_type or "image/jpeg",
                        "data": attachment.raw_bytes_b64,
                    },
                ]
            )
            resp = await llm.ainvoke([msg])
            return f"[Imagem Descrita]: {str(resp.content).strip()}{caption_part}"

        if attachment.caption and attachment.caption.strip():
            return f"[Imagem Descrita]: {attachment.caption.strip()}"

        return f"[Imagem Descrita (media_id={attachment.media_id})]: Imagem recebida no atendimento."

