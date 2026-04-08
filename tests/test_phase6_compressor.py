"""Phase 6: History Compressor — contract, should_compress, compress.

Tests behavior described in contracts/compressor.py and docs/specs/memory-context.md
(section "Kompressiya"):

- CompressionResult dataclass contract compliance
- HistoryCompressor ABC contract compliance
- should_compress: triggers when working context > 8000 tokens
- compress: LLM summarizes oldest ~1500 tokens, returns CompressionResult
- Fallback on LLM failure: RuntimeError raised (caller truncates)

All LLM interactions are mocked. World State uses real in-memory SQLite.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from contracts.compressor import CompressionResult, HistoryCompressor
from party_of_one.models import (
    Disposition,
    Turn,
    TurnRole,
)
from party_of_one.memory.world_state import WorldStateDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_turn(turn_number: int, content: str, role: TurnRole = TurnRole.DM) -> Turn:
    """Create a Turn with minimal required fields."""
    return Turn(
        id=0, turn_number=turn_number, role=role,
        content=content, created_at=datetime.now(),
    )


def _make_turns(count: int, content_each: str = "A" * 300) -> list[Turn]:
    """Create a list of turns with given content repeated."""
    return [
        _make_turn(i + 1, f"Turn {i+1}: {content_each}", TurnRole.DM)
        for i in range(count)
    ]


def _make_short_turns(count: int) -> list[Turn]:
    """Create turns with very short content (well under threshold)."""
    return [_make_turn(i + 1, "ok", TurnRole.DM) for i in range(count)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test_compressor.db"))


@pytest.fixture
def location(db):
    return db.locations.create_initial(
        name="Dark Cave", description="A damp, dark cave"
    ).id


@pytest.fixture
def player(db, location):
    return db.characters.create(
        name="Hero", role="player", class_="Warrior",
        description="A brave warrior",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=10, willpower=8, hp=6, armor=1, gold=10,
    ).id


# ===========================================================================
# 1. Contract compliance: CompressionResult
# ===========================================================================

class TestCompressionResultContract:
    """CompressionResult dataclass has all required fields per contracts/compressor.py."""

    def test_all_fields_present(self):
        cr = CompressionResult(
            compressed=True, summary="Events summary.",
            turns_compressed=3, from_turn=1, to_turn=3,
        )
        assert cr.compressed is True
        assert isinstance(cr.summary, str)
        assert isinstance(cr.turns_compressed, int)
        assert isinstance(cr.from_turn, int)
        assert isinstance(cr.to_turn, int)

    def test_compressed_false_result(self):
        cr = CompressionResult(
            compressed=False, summary="",
            turns_compressed=0, from_turn=0, to_turn=0,
        )
        assert cr.compressed is False
        assert cr.turns_compressed == 0

    def test_summary_is_string(self):
        cr = CompressionResult(
            compressed=True, summary="The party fought goblins.",
            turns_compressed=5, from_turn=1, to_turn=5,
        )
        assert isinstance(cr.summary, str)
        assert len(cr.summary) > 0

    def test_turn_range_consistency(self):
        cr = CompressionResult(
            compressed=True, summary="Summary.",
            turns_compressed=4, from_turn=3, to_turn=6,
        )
        assert cr.to_turn >= cr.from_turn


# ===========================================================================
# 2. Contract compliance: HistoryCompressor ABC
# ===========================================================================

class TestHistoryCompressorABC:
    """HistoryCompressor is an ABC with required abstract methods per contract."""

    def test_is_abstract_class(self):
        assert hasattr(HistoryCompressor, "__abstractmethods__")

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            HistoryCompressor()

    @pytest.mark.parametrize("method_name", [
        "should_compress",
        "compress",
        "append_world_state_facts",
    ])
    def test_has_abstract_method(self, method_name):
        assert method_name in HistoryCompressor.__abstractmethods__


# ===========================================================================
# 3. should_compress: trigger logic
# ===========================================================================

class TestShouldCompress:
    """should_compress returns True when working context exceeds 8000 tokens.

    Spec: docs/specs/memory-context.md, section "Trigger".
    Contract: contracts/compressor.py, should_compress().
    """

    @pytest.fixture
    def compressor(self, db):
        from party_of_one.compressor import HistoryCompressorImpl
        return HistoryCompressorImpl(db=db)

    def test_empty_turns_no_compress(self, compressor):
        assert compressor.should_compress([]) is False

    def test_short_turns_no_compress(self, compressor):
        turns = _make_short_turns(3)
        assert compressor.should_compress(turns) is False

    def test_single_short_turn_no_compress(self, compressor):
        turns = [_make_turn(1, "Hello")]
        assert compressor.should_compress(turns) is False

    def test_large_content_triggers_compress(self, compressor):
        """Turns with enough text to exceed 8000 tokens should trigger."""
        big_content = "A" * 40000  # ~10000 tokens at ~4 chars/token
        turns = [_make_turn(1, big_content)]
        assert compressor.should_compress(turns) is True

    def test_many_turns_accumulate_over_threshold(self, compressor):
        """Multiple medium turns that together exceed threshold."""
        turns = _make_turns(30, "X" * 1500)  # ~30*375 = ~11250 tokens
        assert compressor.should_compress(turns) is True

    def test_returns_bool(self, compressor):
        result = compressor.should_compress(_make_short_turns(2))
        assert isinstance(result, bool)


# ===========================================================================
# 4. compress: happy path
# ===========================================================================

class TestCompressHappyPath:
    """compress() calls LLM to summarize oldest turns, returns CompressionResult.

    Spec: docs/specs/memory-context.md, section "Process".
    Contract: contracts/compressor.py, compress().
    """

    @pytest.fixture
    def compressor(self, db, location, player):
        from party_of_one.compressor import HistoryCompressorImpl
        return HistoryCompressorImpl(db=db)

    def test_returns_compression_result(self, compressor):
        turns = _make_turns(10, "The party explored the forest. " * 20)
        with patch.object(compressor, "_call_llm", return_value="Party explored."):
            result = compressor.compress(turns)
        assert isinstance(result, CompressionResult)

    def test_compressed_flag_true(self, compressor):
        turns = _make_turns(10, "The party fought goblins. " * 20)
        with patch.object(compressor, "_call_llm", return_value="Party fought."):
            result = compressor.compress(turns)
        assert result.compressed is True

    def test_summary_contains_llm_output(self, compressor):
        llm_summary = "Party crossed the bridge and entered the castle."
        turns = _make_turns(5, "Content " * 50)
        with patch.object(compressor, "_call_llm", return_value=llm_summary):
            result = compressor.compress(turns)
        assert llm_summary in result.summary

    def test_turns_compressed_positive(self, compressor):
        turns = _make_turns(8, "Content " * 50)
        with patch.object(compressor, "_call_llm", return_value="Summary."):
            result = compressor.compress(turns)
        assert result.turns_compressed > 0

    def test_from_to_turn_range_valid(self, compressor):
        turns = _make_turns(6, "Content " * 50)
        with patch.object(compressor, "_call_llm", return_value="Summary."):
            result = compressor.compress(turns)
        assert result.from_turn <= result.to_turn
        assert result.from_turn >= 1


# ===========================================================================
# 5. compress: LLM failure -> fallback
# ===========================================================================

class TestCompressFallback:
    """When LLM call fails, compress() raises RuntimeError.

    Spec: "Timeout or LLM error -> truncate old turns."
    Contract: compress() raises RuntimeError after retries.
    """

    @pytest.fixture
    def compressor(self, db, location, player):
        from party_of_one.compressor import HistoryCompressorImpl
        return HistoryCompressorImpl(db=db)

    def test_llm_failure_raises_runtime_error(self, compressor):
        turns = _make_turns(10, "Content " * 50)
        with patch.object(compressor, "_call_llm", side_effect=Exception("LLM timeout")):
            with pytest.raises(RuntimeError):
                compressor.compress(turns)

    def test_llm_timeout_raises_runtime_error(self, compressor):
        turns = _make_turns(10, "Content " * 50)
        with patch.object(
            compressor, "_call_llm", side_effect=TimeoutError("Request timeout"),
        ):
            with pytest.raises(RuntimeError):
                compressor.compress(turns)
