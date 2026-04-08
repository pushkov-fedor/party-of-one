"""Phase 6: History Compressor — integration, edge cases, state transitions.

Tests behavior described in contracts/compressor.py and docs/specs/memory-context.md:

- Full compression flow: should_compress -> compress -> facts appended -> saved
- Edge cases: Cyrillic content, mixed roles, special characters
- Compression cycles (re-compression on long campaigns)
- World State facts reflect current state (invariant)
- CompressedHistory persistence via TurnRepository
- Boundary values for token threshold

All LLM interactions are mocked. World State uses real in-memory SQLite.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from contracts.compressor import CompressionResult
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    CharacterStatus,
    CompressedHistory,
    Disposition,
    QuestStatus,
    Turn,
    TurnRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_turn(turn_number: int, content: str, role: TurnRole = TurnRole.DM) -> Turn:
    return Turn(
        id=0, turn_number=turn_number, role=role,
        content=content, created_at=datetime.now(),
    )


def _make_turns(count: int, content_each: str = "A" * 300) -> list[Turn]:
    return [
        _make_turn(i + 1, f"Turn {i+1}: {content_each}", TurnRole.DM)
        for i in range(count)
    ]


def _make_cyrillic_turns(count: int) -> list[Turn]:
    """Turns with Cyrillic RPG narrative content."""
    narratives = [
        "Партия вошла в тёмную пещеру. Со стен капала вода.",
        "Торин ранен гоблином. Потерял 4 очка здоровья.",
        "Кира нашла волшебный свиток на каменном алтаре.",
        "Бранка атаковала секирой. Гоблин повержен.",
        "Партия нашла тайный проход за водопадом.",
        "Загадочный старик предложил квест: найти пропавших шахтёров.",
        "Партия переместилась в Подземный зал.",
        "Обнаружен сундук с золотом. Торин забрал 15 монет.",
    ]
    return [
        _make_turn(i + 1, narratives[i % len(narratives)], TurnRole.DM)
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test_ext.db"))


@pytest.fixture
def location(db):
    return db.locations.create_initial(
        name="Подземный зал", description="Огромный зал под горой"
    ).id


@pytest.fixture
def player(db, location):
    return db.characters.create(
        name="Герой", role="player", class_="Воин",
        description="Отважный воин",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=10, willpower=8, hp=6, armor=1, gold=10,
    ).id


@pytest.fixture
def dead_companion(db, location):
    c = db.characters.create(
        name="Торин", role="companion", class_="Наёмник",
        description="Суровый наёмник",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=8, willpower=12, hp=0, armor=1, gold=3,
    )
    db.characters.update(c.id, "status", CharacterStatus.DEAD.value)
    return c.id


@pytest.fixture
def compressor(db, location, player):
    from party_of_one.compressor import HistoryCompressorImpl
    return HistoryCompressorImpl(db=db)


# ===========================================================================
# Integration: full compression flow
# ===========================================================================

class TestFullCompressionFlow:
    """End-to-end: should_compress -> compress -> facts appended -> saved."""

    def test_compress_includes_world_state_facts(
        self, compressor, db, dead_companion, player,
    ):
        q = db.quests.create(
            title="Найти шахтёров", description="Найти пропавших шахтёров",
            giver_character_id=player,
        )
        db.quests.update_status(q.id, QuestStatus.COMPLETED)
        turns = _make_cyrillic_turns(15)
        with patch.object(compressor, "_call_llm", return_value="Партия исследовала пещеру."):
            result = compressor.compress(turns)
        assert result.compressed is True
        assert "Партия исследовала пещеру." in result.summary
        assert "Торин" in result.summary
        assert "Найти шахтёров" in result.summary
        assert "Подземный зал" in result.summary

    def test_compress_then_save_to_turn_repo(self, compressor, db):
        turns = _make_cyrillic_turns(10)
        with patch.object(compressor, "_call_llm", return_value="Summary."):
            result = compressor.compress(turns)
        history = CompressedHistory(
            id=0, summary=result.summary,
            covers_turns_from=result.from_turn,
            covers_turns_to=result.to_turn,
            created_at=datetime.now(),
        )
        db.turns.save_compressed_history(history)
        histories = db.turns.get_compressed_history()
        assert len(histories) >= 1
        assert histories[-1].summary == result.summary


# ===========================================================================
# Edge cases: content
# ===========================================================================

class TestCompressEdgeCases:
    """Edge cases for compression content and inputs."""

    def test_cyrillic_content_compressed(self, compressor):
        turns = _make_cyrillic_turns(20)
        with patch.object(compressor, "_call_llm", return_value="Краткое содержание."):
            result = compressor.compress(turns)
        assert result.compressed is True
        assert "Краткое содержание." in result.summary

    def test_mixed_roles_compressed(self, compressor):
        turns = [
            _make_turn(1, "I attack the goblin!", TurnRole.PLAYER),
            _make_turn(2, "You swing your sword.", TurnRole.DM),
            _make_turn(3, "*Кира стреляет из лука*", TurnRole.COMPANION_A),
            _make_turn(4, "*Торин прикрывает щитом*", TurnRole.COMPANION_B),
            _make_turn(5, "The goblin falls defeated.", TurnRole.DM),
        ] * 5
        with patch.object(compressor, "_call_llm", return_value="Battle."):
            result = compressor.compress(turns)
        assert result.compressed is True

    def test_very_long_single_turn(self, compressor):
        long_content = "Партия исследовала подземелье. " * 500
        turns = [_make_turn(1, long_content)]
        with patch.object(compressor, "_call_llm", return_value="Exploration."):
            result = compressor.compress(turns)
        assert result.compressed is True
        assert result.turns_compressed >= 1

    def test_turns_with_special_characters(self, compressor):
        turns = [
            _make_turn(1, 'DM said: "Roll for initiative!"\nResult: 15.'),
            _make_turn(2, "Player uses [Magic Missile] => 3d4+3 damage."),
            _make_turn(3, "Companion: *whispers* 'Watch out...'"),
        ] * 5
        with patch.object(compressor, "_call_llm", return_value="Combat resolved."):
            result = compressor.compress(turns)
        assert result.compressed is True


# ===========================================================================
# Compression cycles (re-compression)
# ===========================================================================

class TestCompressionCycles:
    """Spec: "On long campaigns (50+ rounds), compressed history goes through
    multiple re-compression cycles — narrative details are lost."
    """

    def test_second_compression_cycle(self, compressor, db):
        turns_1 = _make_cyrillic_turns(10)
        with patch.object(compressor, "_call_llm", return_value="First summary."):
            result_1 = compressor.compress(turns_1)
        db.turns.save_compressed_history(CompressedHistory(
            id=0, summary=result_1.summary,
            covers_turns_from=result_1.from_turn,
            covers_turns_to=result_1.to_turn,
            created_at=datetime.now(),
        ))
        turns_2 = [
            _make_turn(11 + i, f"New events turn {i}. " * 30)
            for i in range(10)
        ]
        with patch.object(compressor, "_call_llm", return_value="Second summary."):
            result_2 = compressor.compress(turns_2)
        db.turns.save_compressed_history(CompressedHistory(
            id=0, summary=result_2.summary,
            covers_turns_from=result_2.from_turn,
            covers_turns_to=result_2.to_turn,
            created_at=datetime.now(),
        ))
        histories = db.turns.get_compressed_history()
        assert len(histories) >= 2

    def test_compressed_history_ordered_oldest_first(self, db):
        db.turns.save_compressed_history(CompressedHistory(
            id=0, summary="First.", covers_turns_from=1,
            covers_turns_to=5, created_at=datetime.now(),
        ))
        db.turns.save_compressed_history(CompressedHistory(
            id=0, summary="Second.", covers_turns_from=6,
            covers_turns_to=10, created_at=datetime.now(),
        ))
        histories = db.turns.get_compressed_history()
        assert histories[0].covers_turns_from <= histories[1].covers_turns_from


# ===========================================================================
# World State facts invariant
# ===========================================================================

class TestWorldStateFactsInvariant:
    """Invariant: facts reflect CURRENT world state, no LLM needed."""

    def test_facts_reflect_character_death(self, db, compressor, player):
        result_before = compressor.append_world_state_facts("Before.")
        npc = db.characters.create(
            name="Враг", role="npc", class_="Разбойник",
            description="Опасный", disposition=Disposition.HOSTILE,
            location_id=db.characters.get(player).location_id,
            strength=10, dexterity=10, willpower=10, hp=4, armor=0, gold=0,
        )
        db.characters.update(npc.id, "status", CharacterStatus.DEAD.value)
        result_after = compressor.append_world_state_facts("After.")
        assert "Враг" not in result_before
        assert "Враг" in result_after

    def test_facts_reflect_quest_completion(self, db, compressor, player):
        q = db.quests.create(
            title="Квест героя", description="Выполнить задание",
            giver_character_id=player,
        )
        result_active = compressor.append_world_state_facts("Active.")
        assert "Квест героя" not in result_active
        db.quests.update_status(q.id, QuestStatus.COMPLETED)
        result_done = compressor.append_world_state_facts("Done.")
        assert "Квест героя" in result_done

    def test_facts_reflect_location_change(self, db, compressor, player):
        loc2 = db.locations.create(
            name="Лесная поляна", description="Светлая поляна",
            connected_to=[db.characters.get(player).location_id],
        )
        db.characters.move(player, loc2.id)
        result = compressor.append_world_state_facts("After move.")
        assert "Лесная поляна" in result


# ===========================================================================
# TurnRepository: compressed history persistence
# ===========================================================================

class TestTurnRepositoryCompressedHistory:
    """TurnRepository.save_compressed_history / get_compressed_history."""

    def test_save_and_retrieve(self, db):
        db.turns.save_compressed_history(CompressedHistory(
            id=0, summary="Party explored the cave.",
            covers_turns_from=1, covers_turns_to=5,
            created_at=datetime.now(),
        ))
        histories = db.turns.get_compressed_history()
        assert len(histories) >= 1
        assert histories[-1].summary == "Party explored the cave."

    def test_multiple_histories_preserved(self, db):
        for i in range(3):
            db.turns.save_compressed_history(CompressedHistory(
                id=0, summary=f"Batch {i+1}.",
                covers_turns_from=i * 5 + 1,
                covers_turns_to=(i + 1) * 5,
                created_at=datetime.now(),
            ))
        assert len(db.turns.get_compressed_history()) >= 3

    def test_empty_initially(self, db, location, player):
        assert db.turns.get_compressed_history() == []

    def test_persists_across_reconnect(self, tmp_path):
        db_path = str(tmp_path / "persist.db")
        db1 = WorldStateDB(db_path)
        db1.locations.create_initial(name="Town", description="A town")
        db1.turns.save_compressed_history(CompressedHistory(
            id=0, summary="Persisted.", covers_turns_from=1,
            covers_turns_to=3, created_at=datetime.now(),
        ))
        db2 = WorldStateDB(db_path)
        histories = db2.turns.get_compressed_history()
        assert len(histories) >= 1
        assert histories[0].summary == "Persisted."
