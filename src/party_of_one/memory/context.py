"""Context utilities — helpers for building LLM context fragments."""

from __future__ import annotations

from party_of_one.models import Turn


def format_turn(turn: Turn) -> str:
    """Format a single turn for inclusion in prompts."""
    labels = {
        "player": "Player", "dm": "DM",
        "companion_a": "Companion A", "companion_b": "Companion B",
    }
    role_str = turn.role.value if hasattr(turn.role, "value") else turn.role
    return f"[{labels.get(role_str, role_str)}]: {turn.content}"


def format_turns(turns: list[Turn]) -> str:
    """Format a list of turns into a single text block."""
    return "\n".join(format_turn(t) for t in turns)
