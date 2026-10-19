"""Provedor Outbound `ConsoleMock` para Testes e Simulação Local sem Custo (FR-010)."""

from datetime import UTC, datetime


class ConsoleOutboundProvider:
    """Cumpre `OutboundProviderProtocol` imprimindo a mensagem enviada no terminal e guardando histórico em memória."""

    def __init__(self, *, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure
        self.sent_messages: list[tuple[str, str]] = []

    async def send_text(self, recipient_phone: str, text: str) -> bool:
        """Simula o envio HTTP para o número de destino."""
        if self.simulate_failure:
            return False

        now_iso = datetime.now(UTC).strftime("%H:%M:%S")
        print(f"\n📤 [ConsoleOutbound | {now_iso}] Para +{recipient_phone}: {text}\n", flush=True)
        self.sent_messages.append((recipient_phone, text))
        return True

