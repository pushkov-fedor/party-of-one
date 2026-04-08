"""Phase 1: Tool Executor tests — through repositories."""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import Disposition
from party_of_one.tools.world import ToolExecutor


@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test.db"))

@pytest.fixture
def executor(db):
    return ToolExecutor(db)

@pytest.fixture
def location(db):
    return db.locations.create_initial(name="Arena", description="A fighting arena").id

@pytest.fixture
def character(db, location):
    return db.characters.create(
        name="Fighter", role="player", class_="Warrior", description="Strong",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=18, dexterity=12, willpower=10, hp=10, armor=0, gold=50,
    ).id

@pytest.fixture
def second_character(db, location):
    return db.characters.create(
        name="Mage", role="companion", class_="Wizard", description="Wise",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=8, dexterity=10, willpower=16, hp=4, armor=0, gold=20,
    ).id


class TestRollDiceThroughExecutor:
    def test_returns_result(self, executor):
        r = executor.execute("roll_dice", {"sides": 6, "count": 1})
        assert r.success and "rolls" in r.result

    def test_values_in_range(self, executor):
        r = executor.execute("roll_dice", {"sides": 20, "count": 3})
        assert all(1 <= v <= 20 for v in r.result["rolls"])

class TestMaxDamagePerCall:
    def test_at_limit_accepted(self, executor, character):
        assert executor.execute("damage_character", {"character_id": character, "amount": 50}) is not None

    def test_above_limit_rejected(self, executor, character):
        r = executor.execute("damage_character", {"character_id": character, "amount": 51})
        assert r.success is False and "exceeds max" in r.error

class TestBatchExecution:
    def test_batch_all_commands(self, executor, db, character, second_character):
        cmds = [
            {"name": "damage_character", "args": {"character_id": character, "amount": 2}},
            {"name": "damage_character", "args": {"character_id": second_character, "amount": 1}},
        ]
        executor.execute_batch(cmds)
        assert db.characters.get(character).hp == 8
        assert db.characters.get(second_character).hp == 3

    def test_batch_returns_results(self, executor):
        cmds = [{"name": "roll_dice", "args": {"sides": 6, "count": 1}} for _ in range(2)]
        assert len(executor.execute_batch(cmds)) == 2

class TestBatchAtomicRollback:
    def test_invalid_rolls_back(self, executor, db, character, second_character):
        hp1 = db.characters.get(character).hp
        hp2 = db.characters.get(second_character).hp
        cmds = [
            {"name": "damage_character", "args": {"character_id": character, "amount": 2}},
            {"name": "damage_character", "args": {"character_id": "nonexistent", "amount": 1}},
        ]
        with pytest.raises(Exception):
            executor.execute_batch(cmds)
        assert db.characters.get(character).hp == hp1
        assert db.characters.get(second_character).hp == hp2

    def test_valid_commits(self, executor, db, character):
        hp = db.characters.get(character).hp
        cmds = [{"name": "damage_character", "args": {"character_id": character, "amount": 1}} for _ in range(2)]
        executor.execute_batch(cmds)
        assert db.characters.get(character).hp == hp - 2

class TestMaxCommandsPerTurn:
    def test_ten_accepted(self, executor):
        cmds = [{"name": "roll_dice", "args": {"sides": 6, "count": 1}} for _ in range(10)]
        assert len(executor.execute_batch(cmds)) == 10

    def test_eleven_rejected(self, executor):
        cmds = [{"name": "roll_dice", "args": {"sides": 6, "count": 1}} for _ in range(11)]
        with pytest.raises(ValueError):
            executor.execute_batch(cmds)

class TestToolExecutorEdgeCases:
    def test_unknown_rejected(self, executor):
        with pytest.raises(ValueError):
            executor.execute("nonexistent_command", {})

    def test_empty_batch(self, executor):
        assert executor.execute_batch([]) is not None
