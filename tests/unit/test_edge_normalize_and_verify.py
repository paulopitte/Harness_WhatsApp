"""Testes Unitários da Borda (`edge/`): Verificação HMAC, Sanitização de PII e Normalização (T016)."""

import hashlib
import hmac
import json

import pytest

from harness.domain.exceptions import (
    PayloadNormalizationError,
    SignatureVerificationError,
    UnsupportedMediaError,
)
from harness.domain.value_objects import MediaType
from harness.edge.normalize import (
    build_normalized_text_message,
    parse_webhook_payload,
    sanitize_pii_text,
)
from harness.edge.verify import verify_webhook_signature
from scripts.send_fake_msg import build_meta_payload


def test_verify_webhook_signature_accepts_valid_hmac() -> None:
    secret = "my_super_secret"
    body = b'{"entry": []}'
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    verify_webhook_signature(
        raw_body=body,
        signature_header=f"sha256={digest}",
        app_secret=secret,
        enforce=True,
    )


def test_verify_webhook_signature_rejects_tampered_payload() -> None:
    with pytest.raises(SignatureVerificationError):
        verify_webhook_signature(
            raw_body=b'{"entry": []}',
            signature_header="sha256=invalid_hex_digest",
            app_secret="my_super_secret",
            enforce=True,
        )


def test_sanitize_pii_masks_cpf_and_credit_card() -> None:
    raw = "Meu CPF é 123.456.789-01 e meu cartão 4532 1111 2222 3333."
    sanitized = sanitize_pii_text(raw, enabled=True)
    assert "[CPF_PROTEGIDO]" in sanitized
    assert "[CARTAO_PROTEGIDO]" in sanitized
    assert "123.456.789-01" not in sanitized


def test_parse_webhook_payload_and_build_normalized_message() -> None:
    payload = build_meta_payload(
        phone="5511999998888",
        text="Olá, meu CPF é 111.222.333-44",
        message_id="wamid.test.001",
    )
    events = parse_webhook_payload(payload)
    assert len(events) == 1
    ev = events[0]
    assert ev.provider_message_id == "wamid.test.001"
    assert ev.media_type == MediaType.TEXT

    normalized = build_normalized_text_message(
        ev,
        resolved_text=ev.text_body or "",
        mask_pii=True,
    )
    assert normalized.thread_id == "wa:5511999998888"
    assert "[CPF_PROTEGIDO]" in normalized.text_content


def test_parse_webhook_payload_rejects_missing_entry() -> None:
    with pytest.raises(PayloadNormalizationError):
        parse_webhook_payload(json.loads('{"invalid": true}'))


def test_build_normalized_message_raises_on_unsupported_video() -> None:
    payload = build_meta_payload(
        phone="5511999998888",
        text="",
        msg_type="video",
    )
    events = parse_webhook_payload(payload)
    assert events[0].media_type == MediaType.UNSUPPORTED

    with pytest.raises(UnsupportedMediaError) as exc_info:
        build_normalized_text_message(
            events[0],
            resolved_text="",
            unsupported_reply_text="Vídeo não suportado.",
        )
    assert exc_info.value.reply_text == "Vídeo não suportado."

