"""Party of One — API Contract: Dice.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 3. Dice


def roll_dice(sides: int, count: int = 1) -> DiceResult:
    """Roll *count* dice each with *sides* faces using a local RNG.

    The result is determined by the system random number generator, never
    by the LLM.

    Args:
        sides: Number of faces.  Must be one of {4, 6, 8, 10, 12, 20}.
        count: Number of dice to roll. 1..10.

    Returns:
        ``DiceResult`` with individual rolls and their sum.

    Raises:
        ValueError: If *sides* is not in the allowed set or *count*
            is outside [1, 10].

    Invariants:
        - Each element of ``rolls`` is in [1, sides].
        - ``total == sum(rolls)``.
        - ``len(rolls) == count``.
        - For reproducible tests, seed the RNG externally.
          In production, use ``random.SystemRandom()``.
    """
    ...
