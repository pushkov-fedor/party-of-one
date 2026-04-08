"""Dice roller — local RNG, no LLM involvement."""

from __future__ import annotations

import random

from party_of_one.models import DiceResult

VALID_SIDES = frozenset({4, 6, 8, 10, 12, 20})
MAX_COUNT = 10


def roll_dice(
    sides: int,
    count: int = 1,
    rng: random.Random | None = None,
) -> DiceResult:
    """Roll dice and return results.

    Args:
        sides: Number of sides (must be 4, 6, 8, 10, 12, or 20).
        count: Number of dice to roll (1-10).
        rng: Optional RNG instance for reproducible tests.

    Returns:
        DiceResult with individual rolls and their sum.

    Raises:
        ValueError: If sides or count are invalid.
    """
    if sides not in VALID_SIDES:
        raise ValueError(f"Invalid sides={sides}. Must be one of {sorted(VALID_SIDES)}")
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"Invalid count={count}. Must be 1-{MAX_COUNT}")

    _rng = rng or random.SystemRandom()
    rolls = [_rng.randint(1, sides) for _ in range(count)]
    return DiceResult(rolls=rolls, total=sum(rolls))
