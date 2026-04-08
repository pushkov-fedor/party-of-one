"""Phase 0: Dice roller tests.

Tests behavior described in docs/specs/tools-apis.md (Dice Roller section):
- Valid sides: 4, 6, 8, 10, 12, 20
- Invalid sides are rejected
- Count range: 1-10
- Reproducibility with seed
- All roll values fall within [1, sides]
- Returns DiceResult dataclass
"""

import random

import pytest

from party_of_one.tools.dice import roll_dice


# ---------------------------------------------------------------------------
# Valid dice sides
# ---------------------------------------------------------------------------

VALID_SIDES = [4, 6, 8, 10, 12, 20]


class TestValidDiceSides:
    """roll_dice accepts only the standard RPG dice set: d4, d6, d8, d10, d12, d20."""

    @pytest.mark.parametrize("sides", VALID_SIDES)
    def test_valid_sides_accepted(self, sides):
        result = roll_dice(sides=sides, count=1)
        assert hasattr(result, "rolls")
        assert hasattr(result, "total")

    @pytest.mark.parametrize("sides", VALID_SIDES)
    def test_single_roll_value_within_range(self, sides):
        result = roll_dice(sides=sides, count=1)
        assert len(result.rolls) == 1
        assert 1 <= result.rolls[0] <= sides

    @pytest.mark.parametrize("sides", VALID_SIDES)
    def test_total_equals_sum_of_rolls(self, sides):
        result = roll_dice(sides=sides, count=3)
        assert result.total == sum(result.rolls)


# ---------------------------------------------------------------------------
# Invalid dice sides
# ---------------------------------------------------------------------------

INVALID_SIDES = [0, 1, 2, 3, 5, 7, 9, 11, 13, 15, 100, -1]


class TestInvalidDiceSides:
    """Non-standard die sizes must be rejected."""

    @pytest.mark.parametrize("sides", INVALID_SIDES)
    def test_invalid_sides_rejected(self, sides):
        with pytest.raises((ValueError, Exception)):
            roll_dice(sides=sides, count=1)


# ---------------------------------------------------------------------------
# Count validation
# ---------------------------------------------------------------------------

class TestDiceCount:
    """Count must be between 1 and 10 inclusive."""

    @pytest.mark.parametrize("count", [1, 2, 5, 10])
    def test_valid_count_produces_correct_number_of_rolls(self, count):
        result = roll_dice(sides=6, count=count)
        assert len(result.rolls) == count

    @pytest.mark.parametrize("count", [0, -1, 11, 100])
    def test_invalid_count_rejected(self, count):
        with pytest.raises((ValueError, Exception)):
            roll_dice(sides=6, count=count)


# ---------------------------------------------------------------------------
# Reproducibility with seed
# ---------------------------------------------------------------------------

class TestDiceReproducibility:
    """Fixing the RNG seed produces reproducible results."""

    def test_same_seed_same_result(self):
        rng1 = random.Random(42)
        first = roll_dice(sides=20, count=5, rng=rng1)
        rng2 = random.Random(42)
        second = roll_dice(sides=20, count=5, rng=rng2)
        assert first.rolls == second.rolls
        assert first.total == second.total

    def test_different_seeds_likely_different(self):
        rng1 = random.Random(1)
        first = roll_dice(sides=20, count=5, rng=rng1)
        rng2 = random.Random(999)
        second = roll_dice(sides=20, count=5, rng=rng2)
        assert first.rolls != second.rolls


# ---------------------------------------------------------------------------
# Values always within range (property-based style)
# ---------------------------------------------------------------------------

class TestDiceRangeInvariant:
    """Every individual roll must be between 1 and sides (inclusive)."""

    @pytest.mark.parametrize("sides", VALID_SIDES)
    def test_many_rolls_all_within_range(self, sides):
        for _ in range(50):
            result = roll_dice(sides=sides, count=10)
            for value in result.rolls:
                assert 1 <= value <= sides, (
                    f"d{sides} produced {value}, expected [1, {sides}]"
                )

    @pytest.mark.parametrize("sides", VALID_SIDES)
    def test_total_bounded_by_count_and_sides(self, sides):
        count = 5
        result = roll_dice(sides=sides, count=count)
        assert count <= result.total <= count * sides


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

class TestDiceReturnStructure:
    """roll_dice returns DiceResult with 'rolls' (list of ints) and 'total' (int)."""

    def test_return_has_rolls_attribute(self):
        result = roll_dice(sides=6, count=1)
        assert isinstance(result.rolls, list)

    def test_return_has_total_attribute(self):
        result = roll_dice(sides=6, count=1)
        assert isinstance(result.total, int)

    def test_rolls_are_integers(self):
        result = roll_dice(sides=20, count=3)
        for r in result.rolls:
            assert isinstance(r, int)
