"""Phase 3: Session isolation and restore tests."""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import Disposition, Turn, TurnRole


@pytest.fixture
def db_path_a(tmp_path):
    return str(tmp_path / "session_a.db")

@pytest.fixture
def db_path_b(tmp_path):
    return str(tmp_path / "session_b.db")

def _setup_world(db: WorldStateDB):
    loc = db.locations.create_initial(name="Starting Town", description="A peaceful town")
    char = db.characters.create(
        name="Hero", role="player", class_="Warrior", description="The brave hero",
        disposition=Disposition.FRIENDLY, location_id=loc.id,
        strength=14, dexterity=10, willpower=8, hp=6, armor=1, gold=10,
    )
    return loc.id, char.id


class TestSessionIsolation:
    def test_characters_not_shared(self, db_path_a, db_path_b):
        db_a, db_b = WorldStateDB(db_path_a), WorldStateDB(db_path_b)
        _, char_a = _setup_world(db_a)
        with pytest.raises(KeyError):
            db_b.characters.get(char_a)

    def test_locations_not_shared(self, db_path_a, db_path_b):
        db_a, db_b = WorldStateDB(db_path_a), WorldStateDB(db_path_b)
        loc_a, _ = _setup_world(db_a)
        with pytest.raises(KeyError):
            db_b.locations.get(loc_a)

    def test_modifications_invisible(self, db_path_a, db_path_b):
        db_a, db_b = WorldStateDB(db_path_a), WorldStateDB(db_path_b)
        _, char_a = _setup_world(db_a)
        db_a.characters.damage(char_a, amount=2)
        with pytest.raises(KeyError):
            db_b.characters.get(char_a)


class TestSessionRestore:
    def test_characters_persist(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _, char_id = _setup_world(db1)
        db1.characters.damage(char_id, amount=2)
        expected_hp = db1.characters.get(char_id).hp
        db2 = WorldStateDB(db_path_a)
        assert db2.characters.get(char_id).hp == expected_hp

    def test_locations_persist(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        loc_id, _ = _setup_world(db1)
        db2 = WorldStateDB(db_path_a)
        assert db2.locations.get(loc_id).name == "Starting Town"

    def test_quests_persist(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _, char_id = _setup_world(db1)
        q = db1.quests.create(title="Main Quest", description="Save the world", giver_character_id=char_id)
        db1.quests.update_status(q.id, status="completed")
        db2 = WorldStateDB(db_path_a)
        assert db2.quests.get(q.id).status.value == "completed"

    def test_inventory_persists(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _, char_id = _setup_world(db1)
        db1.characters.add_item(char_id, item="Magic Sword")
        db1.characters.add_item(char_id, item="Great Shield", bulky=True)
        db2 = WorldStateDB(db_path_a)
        names = [i.name for i in db2.characters.get(char_id).inventory]
        assert "Magic Sword" in names and "Great Shield" in names

    def test_gold_persists(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _, char_id = _setup_world(db1)
        db1.characters.update_gold(char_id, amount=-5)
        db2 = WorldStateDB(db_path_a)
        assert db2.characters.get(char_id).gold == 5


class TestTurnsPersistence:
    def test_save_and_retrieve(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _setup_world(db1)
        db1.turns.save_turn(Turn(id=0, turn_number=1, role=TurnRole.DM, content="Welcome!"))
        db2 = WorldStateDB(db_path_a)
        t = db2.turns.get_recent(10)
        assert len(t) >= 1 and t[0].content == "Welcome!"

    def test_multiple_turns_ordered(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _setup_world(db1)
        db1.turns.save_turn(Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="I look around."))
        db1.turns.save_turn(Turn(id=0, turn_number=2, role=TurnRole.DM, content="You see a cave."))
        db1.turns.save_turn(Turn(id=0, turn_number=3, role=TurnRole.COMPANION_A, content="I check entrance."))
        db2 = WorldStateDB(db_path_a)
        nums = [t.turn_number for t in db2.turns.get_recent(10)]
        assert nums == sorted(nums)

    def test_init_saves_turn(self, db_path_a):
        db1 = WorldStateDB(db_path_a)
        _setup_world(db1)
        db1.turns.save_turn(Turn(id=0, turn_number=0, role=TurnRole.DM, content="The adventure begins..."))
        db2 = WorldStateDB(db_path_a)
        assert len(db2.turns.get_recent(10)) >= 1
