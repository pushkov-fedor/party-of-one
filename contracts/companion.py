"""Party of One — API Contract: Companion.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 7. Companion Agent


@runtime_checkable
class CompanionAgent(Protocol):
    """Companion Agent -- an independent AI-controlled party member.

    Each companion has a fixed personality profile and makes its own
    decisions.  It may disagree with the player if that fits the
    character.

    Returns free text in first person — no tool calls, no structured
    output. The DM resolves the companion's action mechanically.
    """

    def generate_action(
        self,
        *,
        profile: CompanionProfile,
        character: Character,
        world_state_snapshot: str,
        compressed_history: str,
        recent_turns: list[Turn],
    ) -> str:
        """Generate a companion's action as free text in first person.

        Args:
            profile: The companion's personality profile.
            character: The companion's current Character record.
            world_state_snapshot: Textual snapshot from
                ``WorldStateDB.snapshot()``.
            compressed_history: Compressed past events summary.
            recent_turns: The N most recent raw turns.

        Returns:
            Free text describing the companion's action and dialogue,
            written in first person (2-3 sentences).
            Fallback on empty/error: ``*{name} выжидает.*``

        Invariants:
            - Temperature: 0.6-0.7.
        """
        ...


def load_companion_profiles(path: str | Path) -> list[CompanionProfile]:
    """Load pre-configured companion profiles from a YAML file.

    Args:
        path: Path to ``data/companions.yaml``.

    Returns:
        List of ``CompanionProfile`` instances.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the YAML structure is invalid or a profile
            is missing required fields.
    """
    ...
