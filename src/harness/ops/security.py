"""Segurança e Autenticação por API Key da Admin API (`ops/security.py` — FR-019, T048).

Equivalente no C#/.NET: `AuthenticationHandler<ApiKeyAuthenticationOptions>` / Endpoint Filter
que valida o header `X-Admin-Api-Key` em tempo constante (`hmac.compare_digest`) e retorna
`HTTP 401 Unauthorized` no padrão RFC 9457 (`ProblemDetails`) em português.
Integra `APIKeyHeader` para habilitar o botão **Authorize** diretamente no Swagger UI (`/docs`).
"""

from collections.abc import Callable
import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

_api_key_header_scheme = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)


def build_admin_api_key_dependency(expected_api_key: str) -> Callable[[str | None], None]:
    """Cria uma dependência FastAPI (`Depends(...)`) que valida o header `X-Admin-Api-Key`."""

    def verify_admin_api_key(
        x_admin_api_key: str | None = Depends(_api_key_header_scheme),
    ) -> None:
        if not x_admin_api_key or not hmac.compare_digest(
            x_admin_api_key.encode("utf-8"),
            expected_api_key.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "type": "https://whatsapp-harness.dev/errors/unauthorized-admin",
                    "title": "Acesso administrativo não autorizado",
                    "status": 401,
                    "detail": "O cabeçalho X-Admin-Api-Key está ausente ou é inválido.",
                },
            )

    return verify_admin_api_key
