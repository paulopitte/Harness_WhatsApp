"""Segurança e Autenticação por API Key da Admin API (`ops/security.py` — FR-019, T048).

Equivalente no C#/.NET: `AuthenticationHandler<ApiKeyAuthenticationOptions>` / Endpoint Filter
que valida o header `X-Admin-Api-Key` em tempo constante (`hmac.compare_digest`) e retorna
`HTTP 401 Unauthorized` no padrão RFC 9457 (`ProblemDetails`) em português.
Integra `APIKeyHeader` para habilitar o botão **Authorize** diretamente no Swagger UI (`/docs`).
"""

import hmac
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader

_api_key_header_scheme = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)


def build_admin_api_key_dependency(expected_api_key: str) -> Callable[..., None]:
    """Cria uma dependência FastAPI (`Depends(...)`) que valida `X-Admin-Api-Key` ou `X-API-Key`."""

    def verify_admin_api_key(
        x_admin_api_key: str | None = Depends(_api_key_header_scheme),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> None:
        provided_key = x_admin_api_key or x_api_key
        if not provided_key or not hmac.compare_digest(
            provided_key.encode("utf-8"),
            expected_api_key.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "type": "https://whatsapp-harness.dev/errors/unauthorized-admin",
                    "title": "Acesso administrativo não autorizado",
                    "status": 401,
                    "detail": (
                        "O cabeçalho X-Admin-Api-Key (ou X-API-Key) está ausente "
                        "ou não corresponde ao ADMIN_API_KEY configurado no .env."
                    ),
                },
            )

    return verify_admin_api_key
