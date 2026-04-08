"""Phase 3: Extended Orchestrator tests.

Tests behavior discovered during real gameplay sessions:

- RoundResult.actor_roles tracks which actors participated in a round
- Round counter persistence: turns survive session save/restore
"""

import pytest

from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    DMResponse,
    RoundResult,
    Turn,
    TurnRole,
)


# ===========================================================================
# RoundResult.actor_roles tracks participating actors
# ===========================================================================

class TestRoundResultActorRoles:
    """RoundResult.actor_roles should list the roles that actually acted in the round.

    Per contract (contracts/orchestrator.py): actor_roles is list[TurnRole]
    indicating who acted: player, companion_a, companion_b.
    """

    def test_full_round_has_all_three_actors(self):
        """When all companions are alive, actor_roles contains player + both companions."""
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            session_ended=False,
        )
        assert TurnRole.PLAYER in rr.actor_roles
        assert TurnRole.COMPANION_A in rr.actor_roles
        assert TurnRole.COMPANION_B in rr.actor_roles
        assert len(rr.actor_roles) == 3

    def test_round_with_one_companion_dead_has_two_actors(self):
        """When one companion is dead, actor_roles has only player + surviving companion."""
        rr = RoundResult(
            round_number=2,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_B],
            session_ended=False,
        )
        assert TurnRole.PLAYER in rr.actor_roles
        assert TurnRole.COMPANION_A not in rr.actor_roles
        assert TurnRole.COMPANION_B in rr.actor_roles
        assert len(rr.actor_roles) == 2

    def test_round_with_both_companions_dead_has_only_player(self):
        """When both companions are dead, only the player acts."""
        rr = RoundResult(
            round_number=3,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER],
            session_ended=False,
        )
        assert rr.actor_roles == [TurnRole.PLAYER]

    def test_actor_roles_never_contains_dm(self):
        """DM is not an actor -- DM responds to actors. actor_roles should not include DM."""
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            session_ended=False,
        )
        assert TurnRole.DM not in rr.actor_roles

    def test_actor_roles_count_matches_dm_responses_count(self):
        """Each actor gets one DM response, so counts should match."""
        dm_responses = [
            DMResponse(narrative="Response to player", tool_calls=[]),
            DMResponse(narrative="Response to companion A", tool_calls=[]),
            DMResponse(narrative="Response to companion B", tool_calls=[]),
        ]
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=dm_responses,
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            session_ended=False,
        )
        assert len(rr.actor_roles) == len(rr.dm_responses)


# ===========================================================================
# Round Counter Persistence Across Session Restore
# ===========================================================================

class TestRoundCounterPersistence:
    """Round counter must persist correctly across session save/restore.

    Session model (contracts/models.py) has round_count: int.
    After N rounds, restoring the session should show the correct round number.
    """

    def test_turns_count_persists_across_restore(self, tmp_path):
        """Saved turns are retrievable after reopening the database."""
        db_path = str(tmp_path / "session.db")

        db1 = WorldStateDB(db_path)
        loc = db1.locations.create_initial(name="Town", description="Town")
        # Simulate 3 rounds (each with player + DM = 2 turns minimum)
        for i in range(6):
            role = TurnRole.PLAYER if i % 2 == 0 else TurnRole.DM
            db1.turns.save_turn(
                Turn(id=0, turn_number=i + 1, role=role, content=f"Turn {i + 1}")
            )

        saved_turns = db1.turns.get_recent(100)
        turn_count = len(saved_turns)

        # Restore from same path
        db2 = WorldStateDB(db_path)
        restored_turns = db2.turns.get_recent(100)
        assert len(restored_turns) == turn_count

    def test_turn_numbers_monotonically_increase_after_restore(self, tmp_path):
        """Turn numbers from a restored session should be in ascending order."""
        db_path = str(tmp_path / "session.db")

        db1 = WorldStateDB(db_path)
        db1.locations.create_initial(name="Camp", description="Camp")
        for i in range(4):
            db1.turns.save_turn(
                Turn(id=0, turn_number=i + 1, role=TurnRole.PLAYER, content=f"Turn {i + 1}")
            )

        db2 = WorldStateDB(db_path)
        restored = db2.turns.get_recent(100)
        numbers = [t.turn_number for t in restored]
        assert numbers == sorted(numbers)
        assert numbers == [1, 2, 3, 4]

    def test_max_turn_number_determines_round_position(self, tmp_path):
        """The highest turn_number in the DB tells the orchestrator where to resume."""
        db_path = str(tmp_path / "session.db")

        db1 = WorldStateDB(db_path)
        db1.locations.create_initial(name="Dungeon", description="Dark")
        # Save 18 turns (simulating 3 full rounds of player+DM+compA+DM+compB+DM)
        roles_per_round = [
            TurnRole.PLAYER, TurnRole.DM,
            TurnRole.COMPANION_A, TurnRole.DM,
            TurnRole.COMPANION_B, TurnRole.DM,
        ]
        for i in range(18):  # 3 rounds x 6 turns
            role = roles_per_round[i % 6]
            db1.turns.save_turn(
                Turn(id=0, turn_number=i + 1, role=role, content=f"Turn {i + 1}")
            )

        db2 = WorldStateDB(db_path)
        all_turns = db2.turns.get_recent(100)
        max_turn = max(t.turn_number for t in all_turns)
        assert max_turn == 18  # 3 rounds x 6 turns
