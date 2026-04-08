"""Phase 1: Extended ToolExecutor tests — all 19 tools through the executor.

Existing tests cover: roll_dice, damage_character, batch execution.
This file covers the remaining tools routed through ToolExecutor.execute():

- heal_character
- update_character
- move_entity
- add_event
- update_quest
- add_item / remove_item
- add_fatigue / remove_fatigue
- damage_stat / restore_stat
- update_gold
- create_character
- create_location
- create_quest
- get_entity
- update_location

Also tests referential integrity and business rule validation through executor.
"""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import Disposition, EventType, QuestStatus
from party_of_one.tools.world import ToolExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test.db"))


@pytest.fixture
def executor(db):
    return ToolExecutor(db)


@pytest.fixture
def location(db):
    return db.locations.create_initial(name="Town", description="A small town").id


@pytest.fixture
def second_location(db, location):
    return db.locations.create(name="Cave", description="A dark cave", connected_to=[location]).id


@pytest.fixture
def character(db, location):
    return db.characters.create(
        name="Hero", role="player", class_="Warrior", description="Brave",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=10, willpower=8, hp=6, armor=2, gold=20,
    ).id


@pytest.fixture
def npc(db, location):
    return db.characters.create(
        name="Goblin", role="npc", class_="Monster", description="Sneaky",
        disposition=Disposition.HOSTILE, location_id=location,
        strength=8, dexterity=12, willpower=6, hp=4, armor=0, gold=5,
    ).id


# ===========================================================================
# heal_character
# ===========================================================================

class TestHealCharacterTool:
    def test_heal_succeeds(self, executor, db, character):
        db.characters.damage(character, amount=4)
        r = executor.execute("heal_character", {"character_id": character, "amount": 2})
        assert r.success is True

    def test_heal_nonexistent_character_fails(self, executor):
        r = executor.execute("heal_character", {"character_id": "ghost", "amount": 1})
        assert r.success is False

    def test_heal_dead_character_fails(self, executor, db, character):
        c = db.characters.get(character)
        db.characters.damage(character, amount=c.hp + c.strength)
        r = executor.execute("heal_character", {"character_id": character, "amount": 1})
        assert r.success is False


# ===========================================================================
# update_character
# ===========================================================================

class TestUpdateCharacterTool:
    def test_update_status(self, executor, character):
        r = executor.execute("update_character", {
            "character_id": character, "field": "status", "value": "deprived",
        })
        assert r.success is True

    def test_update_invalid_field_fails(self, executor, character):
        r = executor.execute("update_character", {
            "character_id": character, "field": "hp", "value": "999",
        })
        assert r.success is False

    def test_update_nonexistent_character_fails(self, executor):
        r = executor.execute("update_character", {
            "character_id": "ghost", "field": "status", "value": "alive",
        })
        assert r.success is False


# ===========================================================================
# move_entity
# ===========================================================================

class TestMoveEntityTool:
    def test_move_to_connected_location(self, executor, character, second_location):
        r = executor.execute("move_entity", {
            "entity_id": character, "location_id": second_location,
        })
        assert r.success is True

    def test_move_to_disconnected_fails(self, executor, db, character):
        isolated = db.locations.create_initial(name="Island", description="Remote")
        r = executor.execute("move_entity", {
            "entity_id": character, "location_id": isolated.id,
        })
        assert r.success is False

    def test_move_nonexistent_entity_fails(self, executor, second_location):
        r = executor.execute("move_entity", {
            "entity_id": "ghost", "location_id": second_location,
        })
        assert r.success is False


# ===========================================================================
# add_event
# ===========================================================================

class TestAddEventTool:
    def test_add_event_succeeds(self, executor):
        r = executor.execute("add_event", {
            "description": "Battle started", "event_type": "combat",
        })
        assert r.success is True

    def test_add_event_all_types(self, executor):
        for et in ["combat", "dialogue", "discovery", "quest", "death"]:
            r = executor.execute("add_event", {
                "description": f"Event of type {et}", "event_type": et,
            })
            assert r.success is True, f"Failed for event_type={et}"


# ===========================================================================
# update_quest
# ===========================================================================

class TestUpdateQuestTool:
    def test_update_quest_status(self, executor, db, character):
        q = db.quests.create(title="Test", description="Desc", giver_character_id=character)
        r = executor.execute("update_quest", {"quest_id": q.id, "status": "completed"})
        assert r.success is True

    def test_update_nonexistent_quest_fails(self, executor):
        r = executor.execute("update_quest", {"quest_id": "ghost", "status": "completed"})
        assert r.success is False


# ===========================================================================
# add_item / remove_item
# ===========================================================================

class TestAddItemTool:
    def test_add_item_succeeds(self, executor, character):
        r = executor.execute("add_item", {"character_id": character, "item": "Sword"})
        assert r.success is True

    def test_add_bulky_item(self, executor, character):
        r = executor.execute("add_item", {
            "character_id": character, "item": "Great Axe", "bulky": True,
        })
        assert r.success is True

    def test_add_item_nonexistent_character_fails(self, executor):
        r = executor.execute("add_item", {"character_id": "ghost", "item": "Sword"})
        assert r.success is False


class TestRemoveItemTool:
    def test_remove_item_succeeds(self, executor, db, character):
        db.characters.add_item(character, item="Torch")
        r = executor.execute("remove_item", {"character_id": character, "item": "Torch"})
        assert r.success is True

    def test_remove_nonexistent_item_fails(self, executor, character):
        r = executor.execute("remove_item", {"character_id": character, "item": "Ghost Item"})
        assert r.success is False


# ===========================================================================
# add_fatigue / remove_fatigue
# ===========================================================================

class TestFatigueTool:
    def test_add_fatigue_succeeds(self, executor, character):
        r = executor.execute("add_fatigue", {"character_id": character})
        assert r.success is True

    def test_remove_fatigue_succeeds(self, executor, db, character):
        db.characters.add_fatigue(character)
        r = executor.execute("remove_fatigue", {"character_id": character})
        assert r.success is True

    def test_remove_fatigue_when_none_fails(self, executor, character):
        r = executor.execute("remove_fatigue", {"character_id": character})
        assert r.success is False


# ===========================================================================
# damage_stat / restore_stat
# ===========================================================================

class TestDamageStatTool:
    def test_damage_stat_succeeds(self, executor, character):
        r = executor.execute("damage_stat", {
            "character_id": character, "stat": "dexterity", "amount": 3,
        })
        assert r.success is True

    def test_damage_stat_invalid_stat_fails(self, executor, character):
        r = executor.execute("damage_stat", {
            "character_id": character, "stat": "charisma", "amount": 1,
        })
        assert r.success is False


class TestRestoreStatTool:
    def test_restore_stat_succeeds(self, executor, db, character):
        db.characters.damage_stat(character, stat="strength", amount=5)
        r = executor.execute("restore_stat", {
            "character_id": character, "stat": "strength", "amount": 3,
        })
        assert r.success is True

    def test_restore_stat_nonexistent_fails(self, executor):
        r = executor.execute("restore_stat", {
            "character_id": "ghost", "stat": "strength", "amount": 1,
        })
        assert r.success is False


# ===========================================================================
# update_gold
# ===========================================================================

class TestUpdateGoldTool:
    def test_gain_gold(self, executor, character):
        r = executor.execute("update_gold", {"character_id": character, "amount": 10})
        assert r.success is True

    def test_spend_gold(self, executor, character):
        r = executor.execute("update_gold", {"character_id": character, "amount": -5})
        assert r.success is True

    def test_overspend_fails(self, executor, db, character):
        gold = db.characters.get(character).gold
        r = executor.execute("update_gold", {"character_id": character, "amount": -(gold + 1)})
        assert r.success is False


# ===========================================================================
# create_character
# ===========================================================================

class TestCreateCharacterTool:
    def test_create_npc(self, executor, location):
        r = executor.execute("create_character", {
            "name": "Merchant",
            "role": "npc",
            "class_": "Merchant",
            "description": "A friendly merchant",
            "disposition": "friendly",
            "location_id": location,
            "strength": 8,
            "dexterity": 10,
            "willpower": 12,
            "hp": 5,
            "armor": 0,
            "gold": 50,
        })
        assert r.success is True

    def test_create_companion(self, executor, location):
        """create_character can create companion characters."""
        r = executor.execute("create_character", {
            "name": "NewCompanion",
            "role": "companion",
            "class_": "Ranger",
            "description": "A new ally",
            "disposition": "friendly",
            "location_id": location,
            "strength": 10,
            "dexterity": 12,
            "willpower": 10,
            "hp": 5,
            "armor": 1,
            "gold": 5,
        })
        assert r.success is True

    def test_create_at_nonexistent_location_fails(self, executor):
        r = executor.execute("create_character", {
            "name": "Lost",
            "role": "npc",
            "class_": "Test",
            "description": "No location",
            "disposition": "neutral",
            "location_id": "nonexistent",
            "strength": 10,
            "dexterity": 10,
            "willpower": 10,
            "hp": 5,
        })
        assert r.success is False

    def test_armor_above_max_rejected(self, executor, location):
        """ToolExecutor.execute('create_character') should reject armor > 3."""
        r = executor.execute("create_character", {
            "name": "Tanky",
            "role": "npc",
            "class_": "Knight",
            "description": "Over-armored",
            "disposition": "neutral",
            "location_id": location,
            "strength": 10,
            "dexterity": 10,
            "willpower": 10,
            "hp": 5,
            "armor": 4,
        })
        assert r.success is False


# ===========================================================================
# create_location
# ===========================================================================

class TestCreateLocationTool:
    def test_create_location_succeeds(self, executor, location):
        r = executor.execute("create_location", {
            "name": "New Area",
            "description": "A new area",
            "connected_to": [location],
        })
        assert r.success is True

    def test_create_location_empty_connections_fails(self, executor):
        r = executor.execute("create_location", {
            "name": "Isolated",
            "description": "No connections",
            "connected_to": [],
        })
        assert r.success is False

    def test_create_location_invalid_connection_fails(self, executor):
        r = executor.execute("create_location", {
            "name": "Bad Connection",
            "description": "References nonexistent",
            "connected_to": ["nonexistent-loc"],
        })
        assert r.success is False


# ===========================================================================
# create_quest
# ===========================================================================

class TestCreateQuestTool:
    def test_create_quest_succeeds(self, executor, character):
        r = executor.execute("create_quest", {
            "title": "Save the Village",
            "description": "Protect from goblins",
            "giver_character_id": character,
        })
        assert r.success is True

    def test_create_quest_nonexistent_giver_fails(self, executor):
        r = executor.execute("create_quest", {
            "title": "Ghost Quest",
            "description": "From nobody",
            "giver_character_id": "nonexistent",
        })
        assert r.success is False


# ===========================================================================
# get_entity
# ===========================================================================

class TestGetEntityTool:
    def test_get_character(self, executor, character):
        r = executor.execute("get_entity", {"type": "character", "id": character})
        assert r.success is True

    def test_get_location(self, executor, location):
        r = executor.execute("get_entity", {"type": "location", "id": location})
        assert r.success is True

    def test_get_nonexistent_fails(self, executor):
        r = executor.execute("get_entity", {"type": "character", "id": "ghost"})
        assert r.success is False


# ===========================================================================
# update_location
# ===========================================================================

class TestUpdateLocationTool:
    def test_update_description(self, executor, location):
        r = executor.execute("update_location", {
            "location_id": location,
            "field": "description",
            "value": "An updated town",
        })
        assert r.success is True

    def test_update_discovered(self, executor, location):
        r = executor.execute("update_location", {
            "location_id": location,
            "field": "discovered",
            "value": "true",
        })
        assert r.success is True

    def test_update_nonexistent_fails(self, executor):
        r = executor.execute("update_location", {
            "location_id": "ghost",
            "field": "description",
            "value": "x",
        })
        assert r.success is False


# ===========================================================================
# Referential Integrity Through Executor
# ===========================================================================

class TestReferentialIntegrityThroughExecutor:
    """All entity references should be validated before execution."""

    def test_damage_nonexistent_character(self, executor):
        r = executor.execute("damage_character", {"character_id": "ghost", "amount": 5})
        assert r.success is False

    def test_heal_nonexistent_character(self, executor):
        r = executor.execute("heal_character", {"character_id": "ghost", "amount": 1})
        assert r.success is False

    def test_add_item_nonexistent_character(self, executor):
        r = executor.execute("add_item", {"character_id": "ghost", "item": "Sword"})
        assert r.success is False

    def test_add_fatigue_nonexistent_character(self, executor):
        r = executor.execute("add_fatigue", {"character_id": "ghost"})
        assert r.success is False

    def test_update_gold_nonexistent_character(self, executor):
        r = executor.execute("update_gold", {"character_id": "ghost", "amount": 10})
        assert r.success is False
