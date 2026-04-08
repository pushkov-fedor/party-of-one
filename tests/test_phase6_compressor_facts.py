"""Phase 6: History Compressor — append_world_state_facts tests.

Tests behavior described in contracts/compressor.py and docs/specs/memory-context.md
(section "Дополнение из World State"):

- Appends dead/incapacitated/deprived/paralyzed/delirious characters
- Appends completed/failed quests (NOT active)
- Appends current party location
- Original summary text is preserved
- No LLM involved — pure SELECT from SQLite

Uses real in-memory SQLite, no LLM.
"""

from __future__ import annotations

import pytest

from party_of_one.models import (
    CharacterStatus,
    Disposition,
    QuestStatus,
)
from party_of_one.memory.world_state import WorldStateDB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test_facts.db"))


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


@pytest.fixture
def companion(db, location):
    return db.characters.create(
        name="Kira", role="companion", class_="Ranger",
        description="A quiet ranger",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=10, dexterity=14, willpower=8, hp=6, armor=1, gold=5,
    ).id


@pytest.fixture
def compressor(db, location, player, companion):
    from party_of_one.compressor import HistoryCompressorImpl
    return HistoryCompressorImpl(db=db)


# ===========================================================================
# append_world_state_facts: fact extraction
# ===========================================================================

class TestAppendWorldStateFactsLocation:
    """Location facts per spec: current party location always included."""

    def test_includes_current_location(self, compressor):
        result = compressor.append_world_state_facts("Previous summary.")
        assert "Dark Cave" in result

    def test_no_dead_no_completed_still_has_location(self, compressor):
        result = compressor.append_world_state_facts("Summary.")
        assert "Dark Cave" in result

    def test_empty_summary_gets_facts(self, compressor):
        result = compressor.append_world_state_facts("")
        assert "Dark Cave" in result
        assert len(result) > 0

    def test_returns_string(self, compressor):
        result = compressor.append_world_state_facts("Summary.")
        assert isinstance(result, str)


class TestAppendWorldStateFactsCharacters:
    """Character status facts per spec: non-alive characters listed."""

    def test_includes_dead_character(self, db, compressor, companion):
        db.characters.update(companion, "status", CharacterStatus.DEAD.value)
        result = compressor.append_world_state_facts("Summary.")
        assert "Kira" in result

    def test_includes_incapacitated_character(self, db, compressor, companion):
        db.characters.update(companion, "status", CharacterStatus.INCAPACITATED.value)
        result = compressor.append_world_state_facts("Summary.")
        assert "Kira" in result

    @pytest.mark.parametrize("status", [
        CharacterStatus.DEAD,
        CharacterStatus.INCAPACITATED,
        CharacterStatus.DEPRIVED,
        CharacterStatus.PARALYZED,
        CharacterStatus.DELIRIOUS,
    ])
    def test_all_non_alive_statuses_included(self, db, location, status):
        """Every non-alive status from spec appears in facts."""
        from party_of_one.compressor import HistoryCompressorImpl
        npc = db.characters.create(
            name="TestNPC", role="npc", class_="Monster",
            description="Test", disposition=Disposition.HOSTILE,
            location_id=location, strength=8, dexterity=8,
            willpower=8, hp=4, armor=0, gold=0,
        )
        db.characters.update(npc.id, "status", status.value)
        compressor = HistoryCompressorImpl(db=db)
        result = compressor.append_world_state_facts("")
        assert "TestNPC" in result

    def test_alive_characters_not_in_non_alive_facts(self, compressor):
        """Characters with status=alive should NOT appear as non-alive entries."""
        result = compressor.append_world_state_facts("Summary.")
        lines = result.split("\n")
        non_alive_lines = [
            l for l in lines
            if any(s in l.lower() for s in [
                "dead", "incapacitated", "deprived", "paralyzed", "delirious",
            ])
        ]
        for line in non_alive_lines:
            assert "Hero" not in line or "alive" in line.lower()


class TestAppendWorldStateFactsQuests:
    """Quest facts per spec: completed/failed quests, NOT active."""

    def test_includes_completed_quest(self, db, compressor, player):
        q = db.quests.create(
            title="Find the Key", description="Find the key",
            giver_character_id=player,
        )
        db.quests.update_status(q.id, QuestStatus.COMPLETED)
        result = compressor.append_world_state_facts("Summary.")
        assert "Find the Key" in result

    def test_includes_failed_quest(self, db, compressor, player):
        q = db.quests.create(
            title="Save the Village", description="Save the village",
            giver_character_id=player,
        )
        db.quests.update_status(q.id, QuestStatus.FAILED)
        result = compressor.append_world_state_facts("Summary.")
        assert "Save the Village" in result

    def test_active_quests_not_included(self, db, compressor, player):
        db.quests.create(
            title="Active Quest", description="Still active",
            giver_character_id=player,
        )
        result = compressor.append_world_state_facts("Summary.")
        assert "Active Quest" not in result


class TestAppendWorldStateFactsCombined:
    """Multiple facts combined; original summary preserved."""

    def test_original_summary_preserved(self, compressor):
        original = "The party entered the forest and found a clearing."
        result = compressor.append_world_state_facts(original)
        assert original in result

    def test_multiple_facts_all_present(self, db, compressor, companion, player):
        """Dead chars + failed quest + location all present together."""
        db.characters.update(companion, "status", CharacterStatus.DEAD.value)
        npc = db.characters.create(
            name="Goblin", role="npc", class_="Monster",
            description="A goblin", disposition=Disposition.HOSTILE,
            location_id=db.characters.get(player).location_id,
            strength=8, dexterity=8, willpower=6, hp=4, armor=0, gold=0,
        )
        db.characters.update(npc.id, "status", CharacterStatus.INCAPACITATED.value)
        q = db.quests.create(
            title="Rescue Mission", description="Rescue prisoners",
            giver_character_id=player,
        )
        db.quests.update_status(q.id, QuestStatus.FAILED)
        result = compressor.append_world_state_facts("Summary text.")
        assert "Kira" in result
        assert "Goblin" in result
        assert "Rescue Mission" in result
        assert "Dark Cave" in result
