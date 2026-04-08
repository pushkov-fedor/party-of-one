"""Party of One — API Contract: Guardrails.

Generated from specs in docs/specs/. Do not edit manually.

Pre-LLM: filters player input before it reaches the DM prompt.
Post-LLM: checks DM response for prompt leaks and validates tool calls before execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check."""

    passed: bool
    reason: str | None = None  # why it was blocked (None if passed)


@dataclass
class PostLLMResult:
    """Outcome of post-LLM check — covers both leak detection and command validation."""

    passed: bool
    invalid_commands: list[str] = field(default_factory=list)
    reason: str | None = None


class PreLLMGuardrail(ABC):
    """Filters player input before it enters the DM prompt.

    Three layers:
    1. Regex filter with normalization — catches obvious injection
       patterns (EN + RU) after Unicode NFKC, homoglyph replacement,
       leetspeak substitution, markdown stripping, space collapse.
    2. Embedding similarity — cosine similarity with a bank of known
       injection patterns using the same embedding model as RAG
       (deepvk/USER-bge-m3). Catches semantic bypasses: paraphrases,
       translations, synonyms.
    3. Length check — truncates input exceeding max_input_length.

    Not applied to companion turns or watch mode.
    If blocked — orchestrator returns templated in-character refusal.
    """

    @abstractmethod
    def check(self, player_input: str) -> GuardrailResult:
        """Check player input for injection attempts.

        Rejects empty/whitespace-only input.
        Runs regex first (fast). If regex passes, runs embedding
        similarity (slower but catches semantic bypasses).

        Returns:
            GuardrailResult with passed=False and reason if blocked.
        """
        ...

    @abstractmethod
    def check_embedding(self, player_input: str) -> GuardrailResult:
        """Check player input via embedding similarity with known injections.

        Computes embedding of the input and compares cosine similarity
        against a bank of known injection pattern embeddings.
        If max similarity > threshold — blocked.

        Returns:
            GuardrailResult with passed=False if similar to known injection.
        """
        ...

    @abstractmethod
    def sanitize(self, player_input: str) -> str:
        """Truncate input to max_input_length.

        Returns:
            Truncated string if over limit, original otherwise.
        """
        ...


class PostLLMGuardrail(ABC):
    """Checks DM response before execution.

    Two stages:
    1. Leak detection — substring match of system prompt phrases
       in the DM's narrative (RU + EN translations).

    2. Command validation (three-step):
       a. Schema validation — parameters match the tool's JSON schema.
       b. Referential integrity — all entity IDs exist in the DB.
       c. Business rules — dead characters can't move, HP ≤ max_hp,
          armor ≤ 3, inventory ≤ 10 slots, etc.

    If blocked — orchestrator re-prompts the DM with error description
    (up to max_retries_on_block times).
    """

    @abstractmethod
    def check_narrative(self, narrative: str) -> GuardrailResult:
        """Check DM narrative for system prompt leaks.

        Returns:
            GuardrailResult with passed=False if leak detected.
        """
        ...

    @abstractmethod
    def validate_commands(
        self, commands: list[dict[str, Any]],
    ) -> PostLLMResult:
        """Validate tool calls before execution.

        Three-step validation:
        1. Schema — params match tool JSON schema.
        2. Referential integrity — entity IDs exist.
        3. Business rules — game logic constraints.

        Args:
            commands: List of tool calls, each with "name" and "args".

        Returns:
            PostLLMResult with invalid_commands listing failures.
        """
        ...
