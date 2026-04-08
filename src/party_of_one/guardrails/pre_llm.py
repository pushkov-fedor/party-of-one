"""Pre-LLM Guardrail — filters player input before it reaches the DM prompt.

Three layers:
1. Regex + normalization (fast, <1ms)
2. Embedding similarity (catches semantic bypasses, ~50-100ms)
3. Length truncation
"""

from __future__ import annotations

import re
import unicodedata

from contracts.guardrails import PreLLMGuardrail as PreLLMGuardrailContract
from contracts.guardrails import GuardrailResult

from party_of_one.config import GuardrailsConfig
from party_of_one.logger import get_logger

logger = get_logger()

# ── Normalization ──────────────────────────────────────────────────────────

_LEET_MAP = str.maketrans("013457", "oieasT")

_HOMOGLYPH_MAP = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0456": "i", "\u0445": "x",
})

_MARKDOWN_RE = re.compile(r"[*_~`]")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _MARKDOWN_RE.sub("", text)
    text = text.translate(_HOMOGLYPH_MAP)
    text = text.translate(_LEET_MAP)
    text = re.sub(r"(?<=\b\w) (?=\w\b)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ── Injection patterns ────────────────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s*(all\s*)?previous", re.IGNORECASE),
    re.compile(r"disregard", re.IGNORECASE),
    re.compile(r"new\s*instructions", re.IGNORECASE),
    re.compile(r"you\s*are\s*now", re.IGNORECASE),
    re.compile(r"forget\s*(all\s*)?(previous|above|prior)", re.IGNORECASE),
    re.compile(r"override", re.IGNORECASE),
    re.compile(r"игнорируй\s*(все\s*)?предыдущие", re.IGNORECASE),
    re.compile(r"забудь\s*(все\s*)?(инструкции|предыдущие|правила)", re.IGNORECASE),
    re.compile(r"новые\s*инструкции", re.IGNORECASE),
    re.compile(r"настоящие\s*инструкции", re.IGNORECASE),
    re.compile(r"(ты\s*теперь|отныне\s*ты)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"<system>", re.IGNORECASE),
    re.compile(r"</system>", re.IGNORECASE),
    re.compile(r"your\s*real\s*purpose", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"покажи\s*(свой\s*)?промпт", re.IGNORECASE),
    re.compile(r"твои\s*инструкции", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^assistant\s*:", re.IGNORECASE | re.MULTILINE),
]


class PreLLMGuardrail(PreLLMGuardrailContract):
    """Regex + embedding similarity + length truncation."""

    def __init__(self, config: GuardrailsConfig | None = None):
        self.config = config or GuardrailsConfig()
        self._embedding_detector = None

    def _get_embedding_detector(self):
        if self._embedding_detector is None:
            from party_of_one.guardrails.embedding_detector import EmbeddingDetector
            self._embedding_detector = EmbeddingDetector(
                threshold=self.config.embedding_similarity_threshold,
            )
        return self._embedding_detector

    def check(self, player_input: str) -> GuardrailResult:
        if not self.config.pre_llm_enabled:
            return GuardrailResult(passed=True)

        # Empty / whitespace-only input
        if not player_input.strip():
            return GuardrailResult(passed=False, reason="empty_input")

        # Layer 1: Regex (original + normalized)
        for text in [player_input, _normalize(player_input)]:
            for pattern in _INJECTION_PATTERNS:
                match = pattern.search(text)
                if match:
                    reason = f"injection_detected: '{match.group()}'"
                    logger.warning("pre_llm_blocked", reason=reason,
                                   input_preview=player_input[:100])
                    return GuardrailResult(passed=False, reason=reason)

        # Layer 2: Embedding similarity
        return self.check_embedding(player_input)

    def check_embedding(self, player_input: str) -> GuardrailResult:
        if not self.config.pre_llm_enabled:
            return GuardrailResult(passed=True)

        try:
            detector = self._get_embedding_detector()
            is_blocked, reason = detector.check(player_input)
            if is_blocked:
                return GuardrailResult(passed=False, reason=reason)
        except Exception as e:
            # Embedding failure is not critical — log and pass
            logger.warning("embedding_check_failed", error=str(e))

        return GuardrailResult(passed=True)

    def sanitize(self, player_input: str) -> str:
        max_len = self.config.max_input_length
        if len(player_input) > max_len:
            logger.info("pre_llm_truncated",
                         original_length=len(player_input), max_length=max_len)
            return player_input[:max_len]
        return player_input


# Alias expected by tests
PreLLMGuardrailImpl = PreLLMGuardrail
