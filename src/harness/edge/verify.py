"""Validação criptográfica de assinatura do Webhook da Meta (`X-Hub-Signature-256` — FR-002).

Equivalente no C#/.NET: `HMACSHA256.ComputeHash` com `CryptographicOperations.FixedTimeEquals`
para prevenir ataques de timing (*timing attacks*).
"""

import hashlib
import hmac

from harness.domain.exceptions import SignatureVerificationError


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
    *,
    enforce: bool = True,
) -> None:
    """Valida o cabeçalho `X-Hub-Signature-256` enviado pela Meta Cloud API.

    Se `enforce=False` (modo de simulação local em desenvolvimento), a validação é ignorada.
    Lança `SignatureVerificationError` caso a assinatura esteja ausente ou não corresponda ao payload.
    """
    if not enforce:
        return

    if not signature_header or not signature_header.startswith("sha256="):
        raise SignatureVerificationError(
            "Cabeçalho X-Hub-Signature-256 ausente ou malformado na requisição do webhook."
        )

    received_hex = signature_header.removeprefix("sha256=").strip()
    expected_hex = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hex, expected_hex):
        raise SignatureVerificationError(
            "Assinatura HMAC-SHA256 do webhook não confere com o segredo da aplicação."
        )

