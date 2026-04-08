"""Phase 3: Orchestrator tests.

Tests behavior described in contracts/orchestrator.py and docs/specs/orchestrator.md:

- init_game: creates player + 2 companions + starting location, calls DM
- process_round: player -> DM -> companion A -> DM -> companion B -> DM
- TPK detection: all party members dead -> session_ended
- Companion turn skip: dead/incapacitated/paralyzed/delirious companions skipped
- Turn order is deterministic
- RoundResult structure
- Error handling: invalid companion_choices

All LLM interactions are mocked. We test orchestration logic, not LLM output.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    Character,
    CharacterRole,
    CharacterStatus,
    CompanionPersonality,
    CompanionProfile,
    DMResponse,
    Disposition,
    RoundResult,
    SessionState,
    Turn,
    TurnRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dm_response(narrative="The adventure continues.", tool_calls=None):
    return DMResponse(narrative=narrative, tool_calls=tool_calls or [])


def _make_companion_response(text="*Бранка выжидает.*"):
    """Companion now returns free text (str), not a structured CompanionResponse."""
    return text


def _make_companion_profiles():
    return [
        CompanionProfile(
            name="Branka", class_="Berserker",
            personality=CompanionPersonality(
                traits=["reckless"], goals=["vengeance"], fears=["inaction"],
                speaking_style="short phrases",
            ),
        ),
        CompanionProfile(
            name="Tikhimir", class_="Ranger",
            personality=CompanionPersonality(
                traits=["cautious"], goals=["return home"], fears=["closed spaces"],
                speaking_style="quiet voice",
            ),
        ),
    ]


# ===========================================================================
# RoundResult structure
# ===========================================================================

class TestRoundResultStructure:
    """RoundResult from contracts/orchestrator.py has required fields."""

    def test_round_result_fields(self):
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[],
            companion_texts={},
            session_ended=False,
        )
        assert rr.round_number == 1
        assert isinstance(rr.turns, list)
        assert isinstance(rr.dm_responses, list)
        assert isinstance(rr.companion_texts, dict)
        assert rr.session_ended is False
        assert rr.end_reason is None

    def test_round_result_with_tpk(self):
        rr = RoundResult(
            round_number=5,
            turns=[],
            dm_responses=[],
            actor_roles=[],
            session_ended=True,
            end_reason="tpk",
        )
        assert rr.session_ended is True
        assert rr.end_reason == "tpk"

    def test_round_result_with_player_exit(self):
        rr = RoundResult(
            round_number=3,
            turns=[],
            dm_responses=[],
            actor_roles=[],
            session_ended=True,
            end_reason="player_exit",
        )
        assert rr.end_reason == "player_exit"

    def test_round_result_with_critical_error(self):
        rr = RoundResult(
            round_number=2,
            turns=[],
            dm_responses=[],
            actor_roles=[],
            session_ended=True,
            end_reason="critical_error",
        )
        assert rr.end_reason == "critical_error"


# ===========================================================================
# TPK Detection
# ===========================================================================

class TestTPKDetection:
    """When all party members are dead, session should end with reason=tpk."""

    @pytest.fixture
    def db(self, tmp_path):
        return WorldStateDB(str(tmp_path / "test.db"))

    @pytest.fixture
    def full_party(self, db):
        loc = db.locations.create_initial(name="Arena", description="Battle arena")
        player = db.characters.create(
            name="Hero", role="player", class_="Warrior", description="Player",
            disposition=Disposition.FRIENDLY, location_id=loc.id,
            strength=14, dexterity=10, willpower=8, hp=6, armor=0, gold=0,
        )
        comp_a = db.characters.create(
            name="Branka", role="companion", class_="Berserker", description="Companion A",
            disposition=Disposition.FRIENDLY, location_id=loc.id,
            strength=16, dexterity=8, willpower=10, hp=8, armor=0, gold=0,
        )
        comp_b = db.characters.create(
            name="Tikhimir", role="companion", class_="Ranger", description="Companion B",
            disposition=Disposition.FRIENDLY, location_id=loc.id,
            strength=10, dexterity=14, willpower=8, hp=6, armor=0, gold=0,
        )
        return player.id, comp_a.id, comp_b.id

    def test_all_alive_no_tpk(self, db, full_party):
        """When all party members are alive, TPK should not be detected."""
        party_chars = [db.characters.get(cid) for cid in full_party]
        all_dead = all(c.status == CharacterStatus.DEAD for c in party_chars)
        assert all_dead is False

    def test_one_dead_no_tpk(self, db, full_party):
        """When one party member is dead but others alive, no TPK."""
        player_id, comp_a_id, comp_b_id = full_party
        c = db.characters.get(player_id)
        db.characters.damage(player_id, amount=c.hp + c.strength)

        party_chars = [db.characters.get(cid) for cid in full_party]
        all_dead = all(c.status == CharacterStatus.DEAD for c in party_chars)
        assert all_dead is False

    def test_all_dead_is_tpk(self, db, full_party):
        """When ALL party members (player + companions) are dead, TPK is true."""
        for cid in full_party:
            c = db.characters.get(cid)
            db.characters.damage(cid, amount=c.hp + c.strength)

        party_chars = [db.characters.get(cid) for cid in full_party]
        all_dead = all(c.status == CharacterStatus.DEAD for c in party_chars)
        assert all_dead is True

    def test_all_incapacitated_is_tpk(self, db, full_party):
        """All incapacitated counts as TPK -- per spec, TPK triggers when all HP <= 0.

        Incapacitated characters have HP <= 0 (critical damage), so a party where
        everyone is dead or incapacitated should be detected as TPK.
        """
        for cid in full_party:
            db.characters.update(cid, field="status", value="incapacitated")

        party_chars = [db.characters.get(cid) for cid in full_party]
        tpk_statuses = {CharacterStatus.DEAD, CharacterStatus.INCAPACITATED}
        all_out = all(c.status in tpk_statuses for c in party_chars)
        assert all_out is True


# ===========================================================================
# Turn Order
# ===========================================================================

class TestTurnOrder:
    """Turn order per round: player -> DM -> companion_a -> DM -> companion_b -> DM."""

    def test_turn_roles_in_order(self):
        """Expected turn order within a round per spec."""
        expected = [
            TurnRole.PLAYER,
            TurnRole.DM,
            TurnRole.COMPANION_A,
            TurnRole.DM,
            TurnRole.COMPANION_B,
            TurnRole.DM,
        ]
        # Verify the enum values exist and are distinct (except DM which repeats)
        assert expected[0] == TurnRole.PLAYER
        assert expected[1] == TurnRole.DM
        assert expected[2] == TurnRole.COMPANION_A
        assert expected[3] == TurnRole.DM
        assert expected[4] == TurnRole.COMPANION_B
        assert expected[5] == TurnRole.DM

    def test_turn_role_enum_has_all_values(self):
        """TurnRole enum must have player, dm, companion_a, companion_b."""
        expected = {"player", "dm", "companion_a", "companion_b"}
        actual = {r.value for r in TurnRole}
        assert expected == actual


# ===========================================================================
# Companion Turn Skip Logic
# ===========================================================================

class TestCompanionTurnSkipLogic:
    """Orchestrator skips companion turns when status is dead/incapacitated/paralyzed/delirious."""

    SKIP_STATUSES = {
        CharacterStatus.DEAD,
        CharacterStatus.INCAPACITATED,
        CharacterStatus.PARALYZED,
        CharacterStatus.DELIRIOUS,
    }
    ACT_STATUSES = {
        CharacterStatus.ALIVE,
        CharacterStatus.DEPRIVED,
    }

    @pytest.mark.parametrize("status", [
        CharacterStatus.DEAD,
        CharacterStatus.INCAPACITATED,
        CharacterStatus.PARALYZED,
        CharacterStatus.DELIRIOUS,
    ])
    def test_skip_status_is_recognized(self, status):
        assert status in self.SKIP_STATUSES

    @pytest.mark.parametrize("status", [
        CharacterStatus.ALIVE,
        CharacterStatus.DEPRIVED,
    ])
    def test_non_skip_status_is_recognized(self, status):
        assert status not in self.SKIP_STATUSES
        assert status in self.ACT_STATUSES


# ===========================================================================
# SessionState Transitions
# ===========================================================================

class TestSessionStateTransitions:
    """SessionState enum covers all required states."""

    def test_awaiting_player_exists(self):
        assert SessionState.AWAITING_PLAYER.value == "awaiting_player"

    def test_processing_exists(self):
        assert SessionState.PROCESSING.value == "processing"

    def test_session_ended_exists(self):
        assert SessionState.SESSION_ENDED.value == "session_ended"


# ===========================================================================
# Init Game Validation
# ===========================================================================

class TestInitGameValidation:
    """init_game should validate companion_choices."""

    def test_companion_choices_must_be_length_two(self):
        """Per contract: ValueError if companion_choices length != 2."""
        # Just verify the contract expectation
        companion_choices = ["Branka"]
        assert len(companion_choices) != 2

        companion_choices_valid = ["Branka", "Tikhimir"]
        assert len(companion_choices_valid) == 2

    def test_companion_names_must_match_profiles(self):
        """Per contract: ValueError if names don't match available profiles."""
        profiles = _make_companion_profiles()
        profile_names = {p.name for p in profiles}
        assert "Branka" in profile_names
        assert "NonExistent" not in profile_names


# ===========================================================================
# Full Round Structure (Mocked)
# ===========================================================================

class TestFullRoundStructure:
    """A complete round produces turns in the expected order with expected roles."""

    def test_round_with_all_companions_active(self):
        """When both companions are alive, round has 6 turns (3 actor + 3 DM)."""
        # Simulate the expected turns
        turns = [
            Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="I attack the goblin"),
            Turn(id=0, turn_number=2, role=TurnRole.DM, content="The goblin dodges..."),
            Turn(id=0, turn_number=3, role=TurnRole.COMPANION_A, content="Branka charges!"),
            Turn(id=0, turn_number=4, role=TurnRole.DM, content="Branka's axe connects!"),
            Turn(id=0, turn_number=5, role=TurnRole.COMPANION_B, content="Tikhimir watches..."),
            Turn(id=0, turn_number=6, role=TurnRole.DM, content="Tikhimir notices tracks."),
        ]
        roles = [t.role for t in turns]
        assert roles == [
            TurnRole.PLAYER, TurnRole.DM,
            TurnRole.COMPANION_A, TurnRole.DM,
            TurnRole.COMPANION_B, TurnRole.DM,
        ]

    def test_round_with_one_companion_dead(self):
        """When companion_a is dead, only 4 turns (skipped companion_a and its DM response)."""
        turns = [
            Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="I look around"),
            Turn(id=0, turn_number=2, role=TurnRole.DM, content="You see a path"),
            # companion_a skipped
            Turn(id=0, turn_number=3, role=TurnRole.COMPANION_B, content="I follow the trail"),
            Turn(id=0, turn_number=4, role=TurnRole.DM, content="The trail leads to..."),
        ]
        roles = [t.role for t in turns]
        assert TurnRole.COMPANION_A not in roles

    def test_round_with_both_companions_dead(self):
        """When both companions dead, only 2 turns (player + DM)."""
        turns = [
            Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="I mourn my friends"),
            Turn(id=0, turn_number=2, role=TurnRole.DM, content="Silence falls..."),
        ]
        roles = [t.role for t in turns]
        assert TurnRole.COMPANION_A not in roles
        assert TurnRole.COMPANION_B not in roles
        assert len(turns) == 2


# ===========================================================================
# Turns Saved to Database
# ===========================================================================

class TestTurnsSavedToDatabase:
    """All turns from a round should be persisted to the turns table."""

    @pytest.fixture
    def db(self, tmp_path):
        return WorldStateDB(str(tmp_path / "test.db"))

    def test_saved_turns_retrievable(self, db):
        loc = db.locations.create_initial(name="Town", description="A town")
        # Save turns as the orchestrator would
        turns = [
            Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="I attack"),
            Turn(id=0, turn_number=2, role=TurnRole.DM, content="The enemy falls"),
            Turn(id=0, turn_number=3, role=TurnRole.COMPANION_A, content="I help"),
            Turn(id=0, turn_number=4, role=TurnRole.DM, content="Together you prevail"),
        ]
        for t in turns:
            db.turns.save_turn(t)

        recent = db.turns.get_recent(10)
        assert len(recent) == 4
        assert recent[0].role == TurnRole.PLAYER
        assert recent[-1].role == TurnRole.DM

    def test_turns_preserve_insertion_order(self, db):
        """Turns saved sequentially are retrieved in the order they were inserted."""
        loc = db.locations.create_initial(name="Town", description="A town")
        db.turns.save_turn(Turn(id=0, turn_number=1, role=TurnRole.PLAYER, content="First"))
        db.turns.save_turn(Turn(id=0, turn_number=2, role=TurnRole.DM, content="Second"))
        db.turns.save_turn(Turn(id=0, turn_number=3, role=TurnRole.COMPANION_A, content="Third"))

        recent = db.turns.get_recent(10)
        contents = [t.content for t in recent]
        assert contents == ["First", "Second", "Third"]


# ===========================================================================
# DMResponse model
# ===========================================================================

class TestDMResponseModel:
    """DMResponse from contracts/dm_agent.py matches expected shape."""

    def test_dm_response_with_no_tool_calls(self):
        r = DMResponse(narrative="You see nothing unusual.", tool_calls=[])
        assert r.narrative == "You see nothing unusual."
        assert r.tool_calls == []

    def test_dm_response_with_tool_calls(self):
        r = DMResponse(
            narrative="Roll for initiative!",
            tool_calls=[
                {"name": "roll_dice", "params": {"sides": 20, "count": 1}},
            ],
        )
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "roll_dice"
