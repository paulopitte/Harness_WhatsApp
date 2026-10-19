"""Adaptador Outbound Oficial da Meta WhatsApp Cloud API (`outbound/providers/meta.py` — FR-009, T035).

Equivalente no C#/.NET: `HttpClient` tipado com política de resiliência Polly (`AddStandardResilienceHandler`)
que abre uma NOVA requisição HTTPS (`POST /{api_version}/{phone_number_id}/messages`) para entregar a resposta
ao cliente após o término do processamento assíncrono na fila.
"""

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from harness.domain.exceptions import OutboundDeliveryError


class MetaOutboundProvider:
    """Provedor Outbound assíncrono para envio de mensagens via Meta WhatsApp Cloud API."""

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str = "v21.0",
        timeout_seconds: float = 10.0,
        base_url: str = "https://graph.facebook.com",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._external_client = http_client

    @property
    def endpoint_url(self) -> str:
        return f"{self._base_url}/{self._api_version}/{self._phone_number_id}/messages"

    async def send_text(self, recipient_phone: str, text: str) -> bool:
        """Envia mensagem de texto para a Meta Cloud API com retry exponencial para erros transitórios."""
        if not self._access_token or not self._phone_number_id:
            raise OutboundDeliveryError(
                provider="meta",
                message="Credenciais WHATSAPP_ACCESS_TOKEN ou WHATSAPP_PHONE_NUMBER_ID ausentes.",
            )

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        async def _post_once() -> bool:
            if self._external_client is not None:
                response = await self._external_client.post(
                    self.endpoint_url,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        self.endpoint_url,
                        headers=headers,
                        json=payload,
                    )

            if response.status_code in (200, 201):
                return True

            if response.status_code >= 500 or response.status_code == 429:
                raise httpx.HTTPStatusError(
                    f"Erro transitório da Meta API ({response.status_code}): {response.text}",
                    request=response.request,
                    response=response,
                )

            raise OutboundDeliveryError(
                provider="meta",
                message=f"Rejeitado pela Meta API ({response.status_code}): {response.text}",
            )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.2, min=0.1, max=2.0),
                retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
                reraise=True,
            ):
                with attempt:
                    return await _post_once()
        except OutboundDeliveryError:
            raise
        except Exception as exc:
            raise OutboundDeliveryError(
                provider="meta",
                message=f"Falha ao comunicar com Meta Cloud API após retries: {exc}",
            ) from exc

        return False

