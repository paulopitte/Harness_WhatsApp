"""Borda HTTP FastAPI (`GET /webhook` e `POST /webhook` — FR-001 a FR-006, T025).

Princípio I da Constitution:
- A Borda NUNCA chama a LLM no ciclo do request.
- Valida assinatura, normaliza payload, aplica Fast-Retry + Quarentena (`Edge DLQ`) e enfileira com Debounce,
  devolvendo `HTTP 200 OK` em `< 150ms`.
"""

import json
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from fastapi import APIRouter, FastAPI, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from harness.domain.exceptions import (
    PayloadNormalizationError,
    RateLimitExceededError,
    SignatureVerificationError,
    UnsupportedMediaError,
)
from harness.domain.message import InboundRawEvent
from harness.domain.ports import QueueEnqueuerProtocol
from harness.domain.value_objects import MediaType
from harness.edge.normalize import build_normalized_text_message, parse_webhook_payload
from harness.edge.resilience import (
    QuarantineRepositoryProtocol,
    execute_with_fast_retry,
    send_to_edge_quarantine,
)
from harness.edge.verify import verify_webhook_signature
from harness.outbound.sender import OutboundSender
from harness.settings import HarnessSettings

MediaResolverCallable = Callable[[InboundRawEvent], Awaitable[str]]


async def _default_media_resolver(event: InboundRawEvent) -> str:
    """Resolver padrão de mídia para a Fase 3 (texto direto ou placeholder para áudio/imagem)."""
    if event.media_type == MediaType.TEXT:
        return event.text_body or ""
    if event.media_type == MediaType.AUDIO:
        hint = event.media_attachment.caption if event.media_attachment else None
        return hint or "[Áudio recebido na borda]"
    if event.media_type == MediaType.IMAGE:
        caption = event.media_attachment.caption if event.media_attachment else None
        return f"[Imagem recebida na borda] {caption or ''}".strip()
    return ""


def create_webhook_app(
    settings: HarnessSettings,
    queue_enqueuer: QueueEnqueuerProtocol,
    quarantine_repo: QuarantineRepositoryProtocol,
    outbound_sender: OutboundSender | None = None,
    *,
    media_resolver: MediaResolverCallable | None = None,
    rate_limiter: Callable[[str], Awaitable[None]] | None = None,
) -> FastAPI:
    """Fábrica da aplicação FastAPI da Borda (`edge/webhook.py`)."""
    app = FastAPI(
        title="WhatsApp Harness — Edge Webhook API",
        version="0.1.0",
        description="Borda HTTP assíncrona de baixa latência (ACK < 150ms, Debounce e Quarentena Edge DLQ).",
    )
    router = APIRouter()
    resolve_media = media_resolver or _default_media_resolver

    @router.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "component": "edge-webhook"}

    @router.get("/webhook")
    async def verify_challenge(
        hub_mode: str | None = Query(default=None, alias="hub.mode"),
        hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    ) -> Response:
        """Desafio GET de verificação do Webhook da Meta Cloud API."""
        if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
            return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "type": "https://whatsapp-harness.dev/errors/invalid-verify-token",
                "title": "Token de verificação inválido",
                "status": 403,
                "detail": "O parâmetro hub.verify_token informado não confere com a configuração da borda.",
            },
        )

    @router.post("/webhook")
    async def receive_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    ) -> Response:
        """Recebe eventos POST da Meta Cloud API / Simulador Local e responde ACK rápido."""
        raw_body = await request.body()
        req_headers = dict(request.headers)

        # 1. Validação Criptográfica de Assinatura (FR-002)
        try:
            verify_webhook_signature(
                raw_body=raw_body,
                signature_header=x_hub_signature_256,
                app_secret=settings.whatsapp_app_secret,
                enforce=settings.edge.verify_signature,
            )
        except SignatureVerificationError as exc:
            await send_to_edge_quarantine(
                quarantine_repo,
                raw_payload={"raw_body_preview": raw_body.decode("utf-8", errors="replace")[:500]},
                headers=req_headers,
                error_reason=exc.message,
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "https://whatsapp-harness.dev/errors/invalid-signature",
                    "title": "Assinatura inválida",
                    "status": 401,
                    "detail": exc.message,
                },
            )

        # 2. Parse do JSON e Extração na Camada Anticorrupção (FR-004)
        try:
            payload_dict: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
            events = parse_webhook_payload(payload_dict)
        except (json.JSONDecodeError, PayloadNormalizationError, UnicodeDecodeError) as exc:
            await send_to_edge_quarantine(
                quarantine_repo,
                raw_payload={"corrupt_body": raw_body.decode("utf-8", errors="replace")[:1000]},
                headers=req_headers,
                error_reason=str(exc),
            )
            # Retorna 200 OK com disposition="quarantined" para evitar loop de retries da Meta
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "accepted", "disposition": "quarantined"},
            )

        if not events:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "accepted", "disposition": "ignored_non_message"},
            )

        dispositions: list[str] = []

        for event in events:
            # 3. Proteção Anti-Loop / Rate Limit por Telefone (FR-001 / US2)
            if rate_limiter is not None:
                try:
                    await rate_limiter(event.sender_phone)
                except RateLimitExceededError:
                    dispositions.append("rate_limited")
                    continue

            # 4. Resolução de Mídia na Borda + Normalização para Texto (FR-016)
            try:
                resolved_text = await resolve_media(event)
                normalized_msg = build_normalized_text_message(
                    event,
                    resolved_text=resolved_text,
                    mask_pii=settings.guardrails.mask_pii_at_edge,
                    unsupported_reply_text=settings.edge.media.unsupported_reply_text,
                )
            except UnsupportedMediaError as exc:
                if outbound_sender is not None:
                    await outbound_sender.deliver(
                        recipient_phone=event.sender_phone,
                        text=exc.reply_text,
                    )
                dispositions.append("unsupported_media_refused")
                continue
            except Exception as exc:
                await send_to_edge_quarantine(
                    quarantine_repo,
                    raw_payload=event.raw_payload,
                    headers=req_headers,
                    error_reason=f"Media/Normalization Failure: {exc}",
                    provider_message_id=event.provider_message_id,
                )
                dispositions.append("quarantined")
                continue

            # 5. Enfileiramento com Fast-Retry (`tenacity`) e Debounce Persistido (FR-003, FR-005, FR-006)
            try:
                queued_id = await execute_with_fast_retry(
                    partial(
                        queue_enqueuer.enqueue_with_debounce,
                        normalized_msg,
                        debounce_seconds=settings.queue.debounce_seconds,
                    ),
                    attempts=settings.edge.fast_retry_attempts,
                    initial_wait_ms=settings.edge.fast_retry_initial_wait_ms,
                )
                dispositions.append("queued" if queued_id is not None else "deduplicated_or_human")
            except (OSError, TimeoutError, ConnectionError) as exc:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "type": "https://whatsapp-harness.dev/errors/queue-unavailable",
                        "title": "Serviço de fila temporariamente indisponível",
                        "status": 503,
                        "detail": f"Falha de conexão após Fast-Retry: {exc}",
                    },
                )

        primary_disposition = dispositions[0] if len(dispositions) == 1 else dispositions
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "accepted", "disposition": primary_disposition},
        )

    app.include_router(router)
    return app

