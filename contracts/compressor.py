"""Party of One — API Contract: History Compressor.

Generated from specs in docs/specs/memory-context.md. Do not edit manually.

Summarizes old turns when working context exceeds compression_threshold_tokens.
Uses a cheap LLM model (model_cheap) with low temperature (0.2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from contracts.models import CompressedHistory, Turn


@dataclass
class CompressionResult:
    """Outcome of a compression attempt."""

    compressed: bool  # True if compression happened
    summary: str  # the compressed summary text
    turns_compressed: int  # how many turns were compressed
    from_turn: int  # first turn number compressed
    to_turn: int  # last turn number compressed


class HistoryCompressor(ABC):
    """Summarizes old turns to free up working context.

    Trigger: working context exceeds compression_threshold_tokens (~3000).

    Process:
    1. Take oldest ~1500 tokens from working context.
    2. LLM call (temperature=0.2): summarize, preserving key facts.
    3. Append result to compressed history (via TurnRepository).
    4. Append World State facts (dead/incapacitated characters,
       completed/failed quests, current location) — no LLM.

    If compression LLM call fails — truncate old turns instead.
    World State facts are always preserved.
    """

    @abstractmethod
    def should_compress(self, recent_turns: list[Turn]) -> bool:
        """Check if working context exceeds compression threshold.

        Args:
            recent_turns: Current working context turns.

        Returns:
            True if total tokens exceed threshold.
        """
        ...

    @abstractmethod
    def compress(self, turns: list[Turn]) -> CompressionResult:
        """Compress the oldest turns into a summary.

        Takes the oldest ~1500 tokens worth of turns,
        calls LLM to summarize, appends World State facts.

        Args:
            turns: Turns to compress (oldest first).

        Returns:
            CompressionResult with summary and metadata.

        Raises:
            RuntimeError: If LLM call fails after retries.
                Caller should fall back to truncation.
        """
        ...

    @abstractmethod
    def append_world_state_facts(self, summary: str) -> str:
        """Append current World State facts to a summary.

        Appends (no LLM, just SELECT):
        - Characters with non-alive status (dead, incapacitated, etc.)
        - Quests with completed/failed status
        - Current party location

        Args:
            summary: The LLM-generated summary text.

        Returns:
            Summary with appended facts section.
        """
        ...
