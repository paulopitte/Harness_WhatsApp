"""Camada Anticorrupção da Borda (Inbound ACL) — Sanitização de PII e Normalização de Payload.

Responsabilidades únicas (SOLID SRP):
1. Aplicar Fast Guardrail de Borda: mascarar dados sensíveis óbvios (CPF, Cartão de Crédito) com regex
   determinístico a custo zero de LLM (FR-019).
2. Extrair eventos de mensagens do JSON bruto da Meta Cloud API (ou simulador local) em `InboundRawEvent`.
3. Transformar o evento em `NormalizedTextMessage` imutável para a fila (Princípio III da Constitution).
"""

import re
from typing import Any

from harness.domain.exceptions import PayloadNormalizationError, UnsupportedMediaError
from harness.domain.message import InboundMediaAttachment, InboundRawEvent, NormalizedTextMessage
from harness.domain.value_objects import MediaType, PhoneNumber, ThreadId

# Expressões regulares para Fast Guardrail de Borda (mascaramento determinístico de PII)
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def sanitize_pii_text(text: str, *, enabled: bool = True) -> str:
    """Mascara padrões de CPF e número de cartão de crédito antes de persistir na fila."""
    if not enabled:
        return text
    masked = _CPF_RE.sub("[CPF_PROTEGIDO]", text)
    masked = _CREDIT_CARD_RE.sub("[CARTAO_PROTEGIDO]", masked)
    return masked


def parse_webhook_payload(raw_payload: dict[str, Any]) -> list[InboundRawEvent]:
    """Extrai a lista de mensagens recebidas de um payload no padrão Meta WhatsApp Cloud API.

    Ignora eventos de status de entrega (`statuses`) que não representam mensagens do usuário.
    Lança `PayloadNormalizationError` caso o payload esteja estruturalmente corrompido.
    """
    if not isinstance(raw_payload, dict) or "entry" not in raw_payload:
        raise PayloadNormalizationError(
            "Payload do webhook não contém a chave obrigatória 'entry'."
        )

    entries = raw_payload.get("entry")
    if not isinstance(entries, list):
        raise PayloadNormalizationError("O campo 'entry' do webhook deve ser uma lista.")

    events: list[InboundRawEvent] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise PayloadNormalizationError("Elemento inválido dentro de 'entry'.")
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            raise PayloadNormalizationError("O campo 'changes' deve ser uma lista.")

        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue

            contacts = value.get("contacts", [])
            sender_name = "Cliente"
            if isinstance(contacts, list) and contacts and isinstance(contacts[0], dict):
                profile = contacts[0].get("profile", {})
                if isinstance(profile, dict) and profile.get("name"):
                    sender_name = str(profile["name"])

            messages = value.get("messages", [])
            if not isinstance(messages, list):
                raise PayloadNormalizationError("O campo 'messages' deve ser uma lista.")

            for msg in messages:
                if not isinstance(msg, dict):
                    raise PayloadNormalizationError("Objeto de mensagem malformado em 'messages'.")

                msg_id = str(msg.get("id", "")).strip()
                sender_phone = str(msg.get("from", "")).strip()
                msg_type = str(msg.get("type", "text")).strip().lower()

                if not msg_id or not sender_phone:
                    raise PayloadNormalizationError(
                        "Mensagem sem identificador ('id') ou remetente ('from')."
                    )

                # Valida formato do telefone logo na borda
                PhoneNumber(sender_phone)

                if msg_type == "text":
                    text_obj = msg.get("text", {})
                    body = text_obj.get("body", "") if isinstance(text_obj, dict) else ""
                    if not str(body).strip():
                        raise PayloadNormalizationError("Mensagem de texto com corpo vazio.")
                    events.append(
                        InboundRawEvent(
                            provider_message_id=msg_id,
                            sender_phone=sender_phone,
                            sender_name=sender_name,
                            media_type=MediaType.TEXT,
                            text_body=str(body),
                            raw_payload=msg,
                        )
                    )
                elif msg_type in ("audio", "voice"):
                    audio_obj = msg.get(msg_type, {}) if isinstance(msg.get(msg_type), dict) else {}
                    events.append(
                        InboundRawEvent(
                            provider_message_id=msg_id,
                            sender_phone=sender_phone,
                            sender_name=sender_name,
                            media_type=MediaType.AUDIO,
                            media_attachment=InboundMediaAttachment(
                                media_id=str(audio_obj.get("id", msg_id)),
                                mime_type=str(audio_obj.get("mime_type", "audio/ogg")),
                                caption=audio_obj.get("transcript_hint"),
                            ),
                            raw_payload=msg,
                        )
                    )
                elif msg_type == "image":
                    img_obj = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
                    events.append(
                        InboundRawEvent(
                            provider_message_id=msg_id,
                            sender_phone=sender_phone,
                            sender_name=sender_name,
                            media_type=MediaType.IMAGE,
                            media_attachment=InboundMediaAttachment(
                                media_id=str(img_obj.get("id", msg_id)),
                                mime_type=str(img_obj.get("mime_type", "image/jpeg")),
                                caption=img_obj.get("caption"),
                            ),
                            raw_payload=msg,
                        )
                    )
                else:
                    events.append(
                        InboundRawEvent(
                            provider_message_id=msg_id,
                            sender_phone=sender_phone,
                            sender_name=sender_name,
                            media_type=MediaType.UNSUPPORTED,
                            raw_payload=msg,
                        )
                    )

    return events


def build_normalized_text_message(
    event: InboundRawEvent,
    resolved_text: str,
    *,
    mask_pii: bool = True,
    unsupported_reply_text: str = "Formato de mídia não suportado.",
) -> NormalizedTextMessage:
    """Converte um `InboundRawEvent` e seu texto resolvido em `NormalizedTextMessage` imutável."""
    if event.media_type == MediaType.UNSUPPORTED:
        raise UnsupportedMediaError(
            media_type="unsupported",
            reply_text=unsupported_reply_text,
        )

    clean_phone = PhoneNumber(event.sender_phone)
    thread_id = ThreadId.from_phone(clean_phone)
    sanitized_text = sanitize_pii_text(resolved_text, enabled=mask_pii)

    return NormalizedTextMessage(
        provider_message_id=event.provider_message_id,
        thread_id=thread_id.value,
        sender_phone=clean_phone.value,
        sender_name=event.sender_name,
        text_content=sanitized_text,
        original_media_type=event.media_type,
    )

