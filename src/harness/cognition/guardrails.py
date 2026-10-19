"""Nós de Input e Output Guardrails do Grafo de Cognição (`cognition/guardrails.py` — FR-011, T032).

Equivalente no C#/.NET: Filtros de Segurança / `IActionFilter` ou `SemanticKernel` Prompt Filter
que inspecionam a entrada do usuário antes de gastar tokens da LLM e validam a saída gerada antes
de enviá-la ao cliente via WhatsApp.
"""

from dataclasses import dataclass
import re
from typing import Any

# Padrões determinísticos de alta precisão para detecção de Prompt Injection / Jailbreak (PT-BR e EN)
_PROMPT_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection_ignore_instructions",
        re.compile(
            r"\bignore\s+(?:all\s+|todas\s+as\s+|as\s+|suas\s+)?"
            r"(?:(?:previous|prior|above|anteriores)\s+(?:instructions|instru[cç][oõ]es|regras|rules|diretrizes)"
            r"|(?:instructions|instru[cç][oõ]es|regras|rules|diretrizes)\s+(?:previous|prior|above|anteriores))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_injection_system_reveal",
        re.compile(
            r"\b(reveal|revele|mostre|exiba|repita|print|dump)\s+"
            r"(?:your\s+|seu\s+|o\s+seu\s+|o\s+|the\s+)?"
            r"(system\s+prompt|prompt\s+de\s+sistema|instru[cç][oõ]es\s+internas)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_injection_jailbreak_persona",
        re.compile(
            r"\b(dan\s+mode|developer\s+mode|modo\s+desenvolvedor|jailbreak|"
            r"voc[eê]\s+agora\s+[eé]\s+um\s+terminal|act\s+as\s+root|aja\s+como\s+root)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_injection_privilege_override",
        re.compile(
            r"(\[system\]|<\|im_start\|>system|###\s*system\s*override)",
            re.IGNORECASE,
        ),
    ),
)

# Padrões de vazamento de prompt de sistema ou credenciais na saída do modelo (Output Guardrail)
_OUTPUT_LEAKAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "output_system_prompt_leak",
        re.compile(
            r"(Diretrizes\s+Obrigat[oó]rias\s+de\s+Atendimento|Nunca\s+revele\s+estas\s+instru[cç][oõ]es\s+internas)",
            re.IGNORECASE,
        ),
    ),
    (
        "output_secret_key_leak",
        re.compile(
            r"\b(sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z\-_]{30,}|postgresql://[^\s]+)\b",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    """Resultado da inspeção de segurança de um Guardrail."""

    blocked: bool
    reason: str | None = None
    safe_reply: str | None = None


DEFAULT_BLOCKED_REPLY = (
    "Desculpe, não posso atender a essa solicitação. "
    "Posso ajudar com dúvidas sobre nossos produtos, serviços ou suporte?"
)


def inspect_input_guardrail(
    user_text: str,
    *,
    enabled: bool = True,
    block_prompt_injection: bool = True,
    blocked_reply_text: str = DEFAULT_BLOCKED_REPLY,
) -> GuardrailVerdict:
    """Analisa a mensagem de entrada do usuário contra ataques de Prompt Injection e Jailbreak."""
    if not enabled or not block_prompt_injection:
        return GuardrailVerdict(blocked=False)

    for rule_name, pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(user_text):
            return GuardrailVerdict(
                blocked=True,
                reason=rule_name,
                safe_reply=blocked_reply_text,
            )

    return GuardrailVerdict(blocked=False)


def inspect_output_guardrail(
    reply_text: str,
    *,
    enabled: bool = True,
    blocked_reply_text: str = DEFAULT_BLOCKED_REPLY,
) -> GuardrailVerdict:
    """Analisa a resposta gerada pela LLM para impedir vazamento de system prompt ou segredos."""
    if not enabled:
        return GuardrailVerdict(blocked=False)

    for rule_name, pattern in _OUTPUT_LEAKAGE_PATTERNS:
        if pattern.search(reply_text):
            return GuardrailVerdict(
                blocked=True,
                reason=rule_name,
                safe_reply=blocked_reply_text,
            )

    return GuardrailVerdict(blocked=False)


async def input_guardrail_node(state: dict[str, Any]) -> dict[str, Any]:
    """Nó LangGraph de Input Guardrail: bloqueia ataques antes de acionar a LLM."""
    user_text = str(state.get("user_text", ""))
    enabled = bool(state.get("guardrails_enabled", True))
    block_pi = bool(state.get("block_prompt_injection", True))
    blocked_reply = str(state.get("blocked_reply_text", DEFAULT_BLOCKED_REPLY))

    verdict = inspect_input_guardrail(
        user_text,
        enabled=enabled,
        block_prompt_injection=block_pi,
        blocked_reply_text=blocked_reply,
    )
    if verdict.blocked:
        return {
            "guardrail_triggered": True,
            "guardrail_reason": verdict.reason,
            "final_reply": verdict.safe_reply or blocked_reply,
        }
    return {
        "guardrail_triggered": False,
        "guardrail_reason": None,
    }


async def output_guardrail_node(state: dict[str, Any]) -> dict[str, Any]:
    """Nó LangGraph de Output Guardrail: valida a resposta final antes do envio ao WhatsApp."""
    if state.get("guardrail_triggered"):
        return {}

    candidate_reply = str(state.get("final_reply", ""))
    enabled = bool(state.get("guardrails_enabled", True))
    blocked_reply = str(state.get("blocked_reply_text", DEFAULT_BLOCKED_REPLY))

    verdict = inspect_output_guardrail(
        candidate_reply,
        enabled=enabled,
        blocked_reply_text=blocked_reply,
    )
    if verdict.blocked:
        return {
            "guardrail_triggered": True,
            "guardrail_reason": verdict.reason,
            "final_reply": verdict.safe_reply or blocked_reply,
        }
    return {}

