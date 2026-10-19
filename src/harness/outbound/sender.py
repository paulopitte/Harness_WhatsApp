"""Despachante Outbound (`OutboundSender`) — Nova conexão para o provedor com confirmação explícita (Princípio VI)."""

from harness.domain.exceptions import OutboundDeliveryError
from harness.domain.ports import OutboundProviderProtocol


class OutboundSender:
    """Envelopa o provedor Outbound ativo garantindo que falhas de entrega lancem `OutboundDeliveryError`."""

    def __init__(self, provider: OutboundProviderProtocol, provider_name: str = "console") -> None:
        self._provider = provider
        self._provider_name = provider_name

    async def deliver(self, recipient_phone: str, text: str) -> None:
        """Envia o texto ao destinatário e lança `OutboundDeliveryError` caso não seja confirmado."""
        confirmed = await self._provider.send_text(recipient_phone, text)
        if not confirmed:
            raise OutboundDeliveryError(
                provider=self._provider_name,
                message=f"O provedor '{self._provider_name}' não confirmou o envio para {recipient_phone}.",
            )

