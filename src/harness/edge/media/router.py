"""Roteador de Mídia na Borda (`edge/media/router.py` — FR-016, T041).

Equivalente no C#/.NET: Strategy Router na fronteira HTTP que decide:
- `MediaType.TEXT` -> retorna o texto direto
- `MediaType.AUDIO` -> se habilitado, aciona `AudioTranscriber`; senão recusa com `UnsupportedMediaError`
- `MediaType.IMAGE` -> se habilitado, aciona `ImageVisionDescriber`; senão recusa com `UnsupportedMediaError`
- `MediaType.UNSUPPORTED` (vídeo, documento, sticker) -> lança `UnsupportedMediaError` imediatamente,
  sem enfileirar e sem gastar 1 centavo de LLM.
"""

from harness.domain.exceptions import UnsupportedMediaError
from harness.domain.message import InboundMediaAttachment, InboundRawEvent
from harness.domain.value_objects import MediaType
from harness.edge.media.transcribe import AudioTranscriber, AudioTranscriberProtocol
from harness.edge.media.vision import ImageVisionDescriber, ImageVisionDescriberProtocol
from harness.settings import EdgeMediaConfig


class EdgeMediaRouter:
    """Roteador determinístico de mídia na fronteira HTTP (`edge/media/router.py`)."""

    def __init__(
        self,
        media_config: EdgeMediaConfig | None = None,
        *,
        transcriber: AudioTranscriberProtocol | None = None,
        vision_describer: ImageVisionDescriberProtocol | None = None,
    ) -> None:
        self._cfg = media_config or EdgeMediaConfig()
        self._transcriber = transcriber or AudioTranscriber()
        self._vision = vision_describer or ImageVisionDescriber()

    async def resolve_to_text(self, event: InboundRawEvent) -> str:
        """Converte qualquer evento suportado (`text`, `audio`, `image`) em string de texto ou lança `UnsupportedMediaError`."""
        if event.media_type == MediaType.TEXT:
            return event.text_body or ""

        if event.media_type == MediaType.AUDIO:
            if not self._cfg.audio_enabled:
                raise UnsupportedMediaError(
                    media_type="audio",
                    reply_text=self._cfg.unsupported_reply_text,
                    message="Processamento de áudio está desabilitado na borda.",
                )
            attachment = event.media_attachment or InboundMediaAttachment(media_id="audio_unknown")
            return await self._transcriber.transcribe(attachment)

        if event.media_type == MediaType.IMAGE:
            if not self._cfg.image_enabled:
                raise UnsupportedMediaError(
                    media_type="image",
                    reply_text=self._cfg.unsupported_reply_text,
                    message="Processamento de imagem está desabilitado na borda.",
                )
            attachment = event.media_attachment or InboundMediaAttachment(media_id="image_unknown")
            return await self._vision.describe(attachment)

        raise UnsupportedMediaError(
            media_type=str(event.media_type),
            reply_text=self._cfg.unsupported_reply_text,
            message=f"Mídia '{event.media_type}' não é suportada pela borda.",
        )

