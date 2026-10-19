"""Conversor de Áudio para Texto na Borda (`edge/media/transcribe.py` — FR-016, T041).

Regra de Ouro da Harness (Princípio III da Constitution):
Áudios de voz do WhatsApp (`.ogg` / `audio/ogg; codecs=opus`) morrem na borda e são convertidos
em texto estruturado ANTES de entrarem na fila transacional (`NormalizedTextMessage`).
"""

from typing import Protocol, runtime_checkable

from harness.domain.message import InboundMediaAttachment


@runtime_checkable
class AudioTranscriberProtocol(Protocol):
    """Porta de transcrição de áudio na borda."""

    async def transcribe(self, attachment: InboundMediaAttachment) -> str: ...


class AudioTranscriber:
    """Transcritor de áudio na borda (com fallback determinístico local quando offline/simulador)."""

    def __init__(self, *, api_key: str = "", model_name: str = "gemini-2.5-flash") -> None:
        cleaned_key = api_key.strip()
        self._api_key = "" if cleaned_key.startswith("your_") else cleaned_key
        self._model_name = model_name

    async def transcribe(self, attachment: InboundMediaAttachment) -> str:
        """Retorna o texto transcrito do anexo de áudio."""
        if attachment.caption and attachment.caption.strip():
            return f"[Áudio Transcrito]: {attachment.caption.strip()}"

        if attachment.raw_bytes_b64 and self._api_key:
            from langchain_core.messages import HumanMessage
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=self._model_name,
                google_api_key=self._api_key,
                temperature=0.0,
            )
            msg = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Transcreva fielmente este áudio em português do Brasil, sem comentários extras.",
                    },
                    {
                        "type": "media",
                        "mime_type": attachment.mime_type or "audio/ogg",
                        "data": attachment.raw_bytes_b64,
                    },
                ]
            )
            resp = await llm.ainvoke([msg])
            return f"[Áudio Transcrito]: {str(resp.content).strip()}"

        return f"[Áudio Transcrito (media_id={attachment.media_id})]: Solicitação enviada por mensagem de voz."

