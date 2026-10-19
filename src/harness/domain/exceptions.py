"""Hierarquia de Exceções de Domínio (DDD) para a WhatsApp Harness.

Equivalente no C#/.NET: Classes de exceção customizadas herdando de `DomainException : Exception`,
que permitem à borda HTTP ou ao pipeline do worker capturar falhas de negócio específicas sem
depender de `Exception` genérica (Clean Code & SOLID).
"""


class HarnessDomainError(Exception):
    """Exceção base para todos os erros de domínio da WhatsApp Harness."""

    def __init__(self, message: str, *, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class SignatureVerificationError(HarnessDomainError):
    """Lançada quando a assinatura criptográfica X-Hub-Signature-256 do webhook é inválida."""

    def __init__(self, message: str = "Assinatura criptográfica do webhook inválida.") -> None:
        super().__init__(message, code="INVALID_WEBHOOK_SIGNATURE")


class PayloadNormalizationError(HarnessDomainError):
    """Lançada quando o payload bruto do webhook está corrompido ou fora do contrato esperado."""

    def __init__(self, message: str = "Payload do webhook inválido ou corrompido.") -> None:
        super().__init__(message, code="PAYLOAD_NORMALIZATION_ERROR")


class RateLimitExceededError(HarnessDomainError):
    """Lançada quando um telefone excede o limite de mensagens por janela (trava anti-loop)."""

    def __init__(
        self,
        phone_number: str,
        message: str = "Limite de mensagens por minuto excedido para este remetente.",
    ) -> None:
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")
        self.phone_number = phone_number


class UnsupportedMediaError(HarnessDomainError):
    """Lançada na borda quando o usuário envia mídia não suportada (ex.: vídeo ou documento)."""

    def __init__(
        self,
        media_type: str,
        reply_text: str,
        message: str = "Formato de mídia não suportado pela borda.",
    ) -> None:
        super().__init__(message, code="UNSUPPORTED_MEDIA")
        self.media_type = media_type
        self.reply_text = reply_text


class GuardrailBlockedError(HarnessDomainError):
    """Lançada quando um nó de Guardrail (Input ou Output) bloqueia a interação por segurança."""

    def __init__(
        self,
        reason: str,
        safe_reply: str,
    ) -> None:
        super().__init__(f"Bloqueado pelo Guardrail: {reason}", code="GUARDRAIL_BLOCKED")
        self.reason = reason
        self.safe_reply = safe_reply


class TokenBudgetExceededError(HarnessDomainError):
    """Lançada pelo TokenBudgetMiddleware quando a thread atinge o teto diário de tokens."""

    def __init__(
        self,
        thread_id: str,
        tokens_used: int,
        daily_limit: int,
    ) -> None:
        super().__init__(
            f"Orçamento diário de tokens excedido para {thread_id}: {tokens_used}/{daily_limit}.",
            code="TOKEN_BUDGET_EXCEEDED",
        )
        self.thread_id = thread_id
        self.tokens_used = tokens_used
        self.daily_limit = daily_limit


class OutboundDeliveryError(HarnessDomainError):
    """Lançada quando o provedor Outbound falha ao entregar a mensagem de resposta ao WhatsApp."""

    def __init__(
        self,
        provider: str,
        message: str = "Falha na confirmação de envio junto ao provedor outbound.",
    ) -> None:
        super().__init__(message, code="OUTBOUND_DELIVERY_ERROR")
        self.provider = provider

