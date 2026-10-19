"""Simulador CLI de Webhooks do WhatsApp (`scripts/send_fake_msg.py` — FR-011, T027).

Permite disparar payloads idênticos aos da Meta Cloud API para o nosso `/webhook` local,
testando:
- Mensagens simples (`--text "Olá"`)
- Rajadas rápidas de Debounce (`--burst "Oi" "Tudo bem?" "Qual o preço?"`)
- Idempotência de mensagem duplicada (`--duplicate`)
- Quarentena de Borda / Edge DLQ (`--corrupt`)
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import uuid4

import httpx

from harness.settings import get_settings


def build_meta_payload(
    phone: str,
    text: str,
    *,
    message_id: str | None = None,
    sender_name: str = "Paulo Pitte",
    msg_type: str = "text",
) -> dict[str, Any]:
    """Gera um payload JSON compatível com o contrato oficial da Meta WhatsApp Cloud API."""
    wamid = message_id or f"wamid.{uuid4().hex}"
    msg_node: dict[str, Any] = {
        "id": wamid,
        "from": phone,
        "timestamp": str(int(time.time())),
        "type": msg_type,
    }
    if msg_type == "text":
        msg_node["text"] = {"body": text}
    elif msg_type == "audio":
        msg_node["audio"] = {"id": f"media_{uuid4().hex[:8]}", "mime_type": "audio/ogg", "transcript_hint": text}
    elif msg_type == "image":
        msg_node["image"] = {"id": f"media_{uuid4().hex[:8]}", "mime_type": "image/jpeg", "caption": text}
    else:
        msg_node[msg_type] = {"id": f"media_{uuid4().hex[:8]}"}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_SIMULATOR_001",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"wa_id": phone, "profile": {"name": sender_name}}],
                            "messages": [msg_node],
                        },
                    }
                ],
            }
        ],
    }


def compute_signature(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def send_payload(
    client: httpx.AsyncClient,
    url: str,
    raw_body: bytes,
    secret: str,
    label: str,
) -> None:
    sig = compute_signature(raw_body, secret)
    t0 = time.perf_counter()
    resp = await client.post(
        url,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"➡️  [{label}] HTTP {resp.status_code} ({elapsed_ms:.1f}ms) -> {resp.text}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador CLI de Webhooks WhatsApp Harness")
    parser.add_argument("--url", default="http://localhost:8000/webhook", help="URL do webhook local")
    parser.add_argument("--phone", default="5511999998888", help="Telefone do remetente")
    parser.add_argument("--text", default="Olá, gostaria de conhecer os planos!", help="Texto da mensagem")
    parser.add_argument("--burst", nargs="+", help="Dispara uma rajada de mensagens rápidas para testar o Debounce")
    parser.add_argument("--duplicate", action="store_true", help="Envia o mesmo provider_message_id 2 vezes")
    parser.add_argument("--corrupt", action="store_true", help="Envia um JSON corrompido para testar a Edge DLQ")
    parser.add_argument("--media-type", default="text", choices=["text", "audio", "image", "video"])
    args = parser.parse_args()

    settings = get_settings()
    secret = settings.whatsapp_app_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        if args.corrupt:
            await send_payload(
                client,
                args.url,
                b'{"object": "corrupt_payload_without_entry"}',
                secret,
                "CORRUPT -> EDGE DLQ",
            )
            return

        if args.burst:
            for idx, msg_text in enumerate(args.burst, start=1):
                payload = build_meta_payload(args.phone, msg_text, msg_type=args.media_type)
                raw = json.dumps(payload).encode("utf-8")
                await send_payload(client, args.url, raw, secret, f"BURST #{idx}: '{msg_text}'")
                await asyncio.sleep(0.15)
            return

        fixed_id = f"wamid.dup.{uuid4().hex[:12]}" if args.duplicate else None
        payload = build_meta_payload(
            args.phone,
            args.text,
            message_id=fixed_id,
            msg_type=args.media_type,
        )
        raw = json.dumps(payload).encode("utf-8")
        await send_payload(client, args.url, raw, secret, "MSG #1")

        if args.duplicate:
            await send_payload(client, args.url, raw, secret, "MSG #2 (DUPLICADA)")


if __name__ == "__main__":
    asyncio.run(main())

