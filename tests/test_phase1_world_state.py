"""Phase 1: World State tests — repositories + facade."""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import CharacterStatus, Disposition


@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test.db"))

@pytest.fixture
def location(db):
    return db.locations.create_initial(name="Town Square", description="A busy square").id

@pytest.fixture
def character(db, location):
    return db.characters.create(
        name="Hero", role="player", class_="Warrior", description="A brave warrior",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=10, willpower=8, hp=6, armor=1, gold=10,
    ).id

@pytest.fixture
def npc(db, location):
    return db.characters.create(
        name="Goblin", role="npc", class_="Monster", description="A sneaky goblin",
        disposition=Disposition.HOSTILE, location_id=location,
        strength=8, dexterity=12, willpower=6, hp=4, armor=0, gold=2,
    ).id

@pytest.fixture
def companion(db, location):
    return db.characters.create(
        name="Kira", role="companion", class_="Ranger", description="A quiet ranger",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=10, dexterity=14, willpower=8, hp=6, armor=1, gold=5,
    ).id


# === Character CRUD ===

class TestCharacterCreate:
    def test_create_returns_id(self, character):
        assert isinstance(character, str)

    def test_created_character_retrievable(self, db, character):
        assert db.characters.get(character).name == "Hero"

    def test_max_values_set_on_creation(self, db, character):
        c = db.characters.get(character)
        assert c.max_hp == c.hp and c.max_strength == c.strength

    def test_initial_status_is_alive(self, db, character):
        assert db.characters.get(character).status == CharacterStatus.ALIVE

class TestCharacterGet:
    def test_get_existing(self, db, character):
        c = db.characters.get(character)
        assert c.name == "Hero" and c.role.value == "player"

    def test_get_nonexistent_raises(self, db):
        with pytest.raises(KeyError):
            db.characters.get("nonexistent-id-xxx")

class TestGetAllCharacters:
    def test_get_all(self, db, character, npc, companion):
        assert len(db.characters.get_all()) == 3

    def test_get_all_empty(self, db):
        assert db.characters.get_all() == []


# === Damage Cascade ===

class TestDamageSimple:
    def test_damage_reduces_hp(self, db, character):
        hp_before = db.characters.get(character).hp
        db.characters.damage(character, amount=2)
        assert db.characters.get(character).hp == hp_before - 2

    def test_damage_does_not_affect_strength(self, db, character):
        s = db.characters.get(character).strength
        db.characters.damage(character, amount=1)
        assert db.characters.get(character).strength == s

class TestDamageHPZeroScarRoll:
    def test_hp_zero_triggers_scar_roll(self, db, character):
        hp = db.characters.get(character).hp
        result = db.characters.damage(character, amount=hp)
        assert db.characters.get(character).hp == 0
        assert result.requires_scar_roll is True

class TestDamageOverflowToStrength:
    def test_overflow_damage_reduces_strength(self, db, character):
        c = db.characters.get(character)
        db.characters.damage(character, amount=c.hp + 3)
        after = db.characters.get(character)
        assert after.hp == 0 and after.strength == c.strength - 3

    def test_overflow_triggers_str_save(self, db, character):
        hp = db.characters.get(character).hp
        assert db.characters.damage(character, amount=hp + 1).requires_str_save is True

class TestDamageStrengthZeroDeath:
    def test_str_zero_sets_dead(self, db, character):
        c = db.characters.get(character)
        result = db.characters.damage(character, amount=c.hp + c.strength)
        assert db.characters.get(character).status == CharacterStatus.DEAD
        assert result.character_died is True

class TestDamageDeadCharacter:
    def test_damage_dead_raises(self, db, character):
        c = db.characters.get(character)
        db.characters.damage(character, amount=c.hp + c.strength)
        with pytest.raises(ValueError):
            db.characters.damage(character, amount=1)


# === Heal ===

class TestHeal:
    def test_heal_increases_hp(self, db, character):
        db.characters.damage(character, amount=3)
        hp_d = db.characters.get(character).hp
        db.characters.heal(character, amount=2)
        assert db.characters.get(character).hp == hp_d + 2

    def test_heal_caps_at_max_hp(self, db, character):
        db.characters.damage(character, amount=1)
        db.characters.heal(character, amount=100)
        c = db.characters.get(character)
        assert c.hp == c.max_hp

    def test_deprived_cannot_heal(self, db, character):
        db.characters.damage(character, amount=2)
        db.characters.update(character, field="status", value="deprived")
        with pytest.raises(ValueError):
            db.characters.heal(character, amount=1)


# === Stat Damage ===

class TestStatDamage:
    def test_damage_dexterity(self, db, character):
        before = db.characters.get(character).dexterity
        assert db.characters.damage_stat(character, stat="dexterity", amount=3) == before - 3

    def test_dex_zero_sets_paralyzed(self, db, character):
        dex = db.characters.get(character).dexterity
        db.characters.damage_stat(character, stat="dexterity", amount=dex)
        assert db.characters.get(character).status == CharacterStatus.PARALYZED

    def test_wil_zero_sets_delirious(self, db, character):
        wil = db.characters.get(character).willpower
        db.characters.damage_stat(character, stat="willpower", amount=wil)
        assert db.characters.get(character).status == CharacterStatus.DELIRIOUS

    def test_str_zero_sets_dead(self, db, character):
        s = db.characters.get(character).strength
        db.characters.damage_stat(character, stat="strength", amount=s)
        assert db.characters.get(character).status == CharacterStatus.DEAD

    def test_dead_cannot_take_stat_damage(self, db, character):
        s = db.characters.get(character).strength
        db.characters.damage_stat(character, stat="strength", amount=s)
        with pytest.raises(ValueError):
            db.characters.damage_stat(character, stat="dexterity", amount=1)


# === Restore Stat ===

class TestRestoreStat:
    def test_restore_strength(self, db, character):
        db.characters.damage_stat(character, stat="strength", amount=5)
        db.characters.restore_stat(character, stat="strength", amount=3)
        c = db.characters.get(character)
        assert c.strength == c.max_strength - 5 + 3

    def test_restore_caps_at_max(self, db, character):
        db.characters.damage_stat(character, stat="dexterity", amount=2)
        db.characters.restore_stat(character, stat="dexterity", amount=100)
        c = db.characters.get(character)
        assert c.dexterity == c.max_dexterity

    def test_deprived_cannot_restore(self, db, character):
        db.characters.damage_stat(character, stat="strength", amount=3)
        db.characters.update(character, field="status", value="deprived")
        with pytest.raises(ValueError):
            db.characters.restore_stat(character, stat="strength", amount=1)


# === Inventory ===

class TestInventoryAddItem:
    def test_add_normal_item(self, db, character):
        inv = db.characters.add_item(character, item="Sword")
        assert "Sword" in [i.name for i in inv]

    def test_add_bulky_item_takes_two_slots(self, db, character):
        inv = db.characters.add_item(character, item="Great Axe", bulky=True)
        assert [i for i in inv if i.name == "Great Axe"][0].slots == 2

    def test_max_slots_respected(self, db, character):
        for i in range(10):
            db.characters.add_item(character, item=f"Item_{i}")
        with pytest.raises(ValueError):
            db.characters.add_item(character, item="One Too Many")

    def test_overload_sets_hp_to_zero(self, db, character):
        for i in range(10):
            db.characters.add_item(character, item=f"Item_{i}")
        assert db.characters.get(character).hp == 0

class TestInventoryRemoveItem:
    def test_remove_existing(self, db, character):
        db.characters.add_item(character, item="Torch")
        inv = db.characters.remove_item(character, item="Torch")
        assert "Torch" not in [i.name for i in inv]

    def test_remove_nonexistent_raises(self, db, character):
        with pytest.raises(ValueError):
            db.characters.remove_item(character, item="Nonexistent")


# === Fatigue ===

class TestFatigue:
    def test_add_increments(self, db, character):
        assert db.characters.add_fatigue(character) == 1

    def test_remove_decrements(self, db, character):
        db.characters.add_fatigue(character)
        db.characters.add_fatigue(character)
        assert db.characters.remove_fatigue(character) == 1

    def test_fatigue_plus_items_overload(self, db, character):
        for i in range(8):
            db.characters.add_item(character, item=f"Item_{i}")
        db.characters.add_fatigue(character)
        db.characters.add_fatigue(character)
        assert db.characters.get(character).hp == 0

    def test_remove_when_none_raises(self, db, character):
        with pytest.raises(ValueError):
            db.characters.remove_fatigue(character)


# === Gold ===

class TestGold:
    def test_gain(self, db, character):
        before = db.characters.get(character).gold
        db.characters.update_gold(character, amount=5)
        assert db.characters.get(character).gold == before + 5

    def test_spend(self, db, character):
        before = db.characters.get(character).gold
        db.characters.update_gold(character, amount=-3)
        assert db.characters.get(character).gold == before - 3

    def test_overspend_raises(self, db, character):
        g = db.characters.get(character).gold
        with pytest.raises(ValueError):
            db.characters.update_gold(character, amount=-(g + 1))


# === Locations ===

class TestLocations:
    def test_create_location(self, db, location):
        loc = db.locations.create(name="Forest", description="Dark forest", connected_to=[location])
        assert loc.id is not None

    def test_create_requires_connected_to(self, db):
        with pytest.raises(ValueError):
            db.locations.create(name="Nowhere", description="Isolated", connected_to=[])

    def test_bidirectional_connections(self, db, location):
        loc_b = db.locations.create(name="Cave", description="Dark cave", connected_to=[location])
        assert location in db.locations.get(loc_b.id).connected_to
        assert loc_b.id in db.locations.get(location).connected_to

class TestMoveEntity:
    def test_move_to_connected(self, db, character, location):
        loc_b = db.locations.create(name="Market", description="Busy", connected_to=[location])
        db.characters.move(character, loc_b.id)
        assert db.characters.get(character).location_id == loc_b.id

    def test_move_to_disconnected_raises(self, db, character, location):
        loc_b = db.locations.create_initial(name="Island", description="Remote")
        with pytest.raises(ValueError):
            db.characters.move(character, loc_b.id)

    def test_dead_cannot_move(self, db, character, location):
        loc_b = db.locations.create(name="Market", description="Busy", connected_to=[location])
        c = db.characters.get(character)
        db.characters.damage(character, amount=c.hp + c.strength)
        with pytest.raises(ValueError):
            db.characters.move(character, loc_b.id)


# === Quests ===

class TestQuests:
    def test_create_quest(self, db, character):
        q = db.quests.create(title="Find sword", description="Legendary", giver_character_id=character)
        assert q.id is not None

    def test_default_status_active(self, db, character):
        q = db.quests.create(title="Rescue", description="Dungeon", giver_character_id=character)
        assert q.status.value == "active"

    def test_update_completed(self, db, character):
        q = db.quests.create(title="Deliver", description="To king", giver_character_id=character)
        db.quests.update_status(q.id, status="completed")
        assert db.quests.get(q.id).status.value == "completed"

    def test_update_failed(self, db, character):
        q = db.quests.create(title="Guard", description="Until dawn", giver_character_id=character)
        db.quests.update_status(q.id, status="failed")
        assert db.quests.get(q.id).status.value == "failed"

    @pytest.mark.parametrize("bad_status", ["done", "cancelled", "pending", ""])
    def test_invalid_status_raises(self, db, character, bad_status):
        q = db.quests.create(title="Test", description="Desc", giver_character_id=character)
        with pytest.raises(ValueError):
            db.quests.update_status(q.id, status=bad_status)


# === Snapshot ===

class TestSnapshot:
    def test_contains_character(self, db, character, npc):
        assert "Hero" in db.snapshot()

    def test_contains_location(self, db, character, location):
        assert "Town Square" in db.snapshot()

    def test_contains_quest(self, db, character):
        db.quests.create(title="Main Quest", description="The quest", giver_character_id=character)
        assert "Main Quest" in db.snapshot()


# === Invariants ===

class TestWorldStateInvariants:
    def test_hp_never_exceeds_max(self, db, character):
        db.characters.heal(character, amount=999)
        c = db.characters.get(character)
        assert c.hp <= c.max_hp

    def test_occupied_slots(self, db, character):
        db.characters.add_item(character, item="Sword")
        db.characters.add_item(character, item="Shield", bulky=True)
        db.characters.add_fatigue(character)
        c = db.characters.get(character)
        assert sum(i.slots for i in c.inventory) + c.fatigue == 1 + 2 + 1

    def test_stats_never_exceed_max(self, db, character):
        db.characters.damage_stat(character, stat="strength", amount=2)
        db.characters.restore_stat(character, stat="strength", amount=999)
        c = db.characters.get(character)
        assert c.strength <= c.max_strength
