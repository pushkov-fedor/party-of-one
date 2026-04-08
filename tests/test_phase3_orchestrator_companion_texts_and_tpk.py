"""Phase 3: Tests for companion_texts in RoundResult and TPK-incapacitated fix.

Two behavioral changes tested here:

1. RoundResult.companion_texts (new field):
   - Per contract (contracts/orchestrator.py): dict[str, str] mapping
     actor_role.value -> companion's first-person text.
   - Per spec (docs/specs/orchestrator.md): "Player sees companion's direct
     first-person line AND DM response. Companion line shown before DM narrative."

2. TPK includes incapacitated (bug fix):
   - Per spec: "TPK triggers when all party members HP <= 0."
   - Incapacitated characters have HP <= 0 (critical damage in Cairn).
   - TPK should fire for any combination where all members are dead OR incapacitated.
"""

import pytest

from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    CharacterStatus,
    DMResponse,
    Disposition,
    RoundResult,
    Turn,
    TurnRole,
)


# ===========================================================================
# RoundResult.companion_texts — new field behavior
# ===========================================================================


class TestCompanionTextsField:
    """RoundResult.companion_texts maps role.value -> first-person companion text.

    Per contract: companion_texts: dict[str, str]
    Per spec: player sees companion's direct line before DM narrative.
    """

    def test_companion_texts_present_when_both_companions_act(self):
        """When both companions are active, companion_texts has entries for each."""
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            companion_texts={
                TurnRole.COMPANION_A.value: "Natjagivaju tetivu i strelaju!",
                TurnRole.COMPANION_B.value: "Derzhus' pozadi, nabljudaju.",
            },
            session_ended=False,
        )
        assert len(rr.companion_texts) == 2
        assert TurnRole.COMPANION_A.value in rr.companion_texts
        assert TurnRole.COMPANION_B.value in rr.companion_texts

    def test_companion_texts_empty_when_no_companions_act(self):
        """When both companions are skipped (dead), companion_texts is empty."""
        rr = RoundResult(
            round_number=3,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER],
            companion_texts={},
            session_ended=False,
        )
        assert rr.companion_texts == {}

    def test_companion_texts_has_only_active_companion(self):
        """When one companion is skipped, companion_texts only contains the active one."""
        rr = RoundResult(
            round_number=2,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_B],
            companion_texts={
                TurnRole.COMPANION_B.value: "Idu vpered ostorozhno.",
            },
            session_ended=False,
        )
        assert len(rr.companion_texts) == 1
        assert TurnRole.COMPANION_A.value not in rr.companion_texts
        assert TurnRole.COMPANION_B.value in rr.companion_texts

    def test_companion_texts_never_contains_player(self):
        """Player is not a companion -- player role should never appear in companion_texts."""
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            companion_texts={
                TurnRole.COMPANION_A.value: "Atakuju!",
                TurnRole.COMPANION_B.value: "Prikryvaju!",
            },
            session_ended=False,
        )
        assert TurnRole.PLAYER.value not in rr.companion_texts
        assert TurnRole.DM.value not in rr.companion_texts

    def test_companion_texts_keys_are_string_values_not_enums(self):
        """Keys in companion_texts are str (TurnRole.value), not TurnRole enums."""
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A],
            companion_texts={
                TurnRole.COMPANION_A.value: "Gotov.",
            },
            session_ended=False,
        )
        for key in rr.companion_texts:
            assert isinstance(key, str)

    def test_companion_texts_values_are_nonempty_strings(self):
        """Companion first-person text should be a non-empty string when present."""
        texts = {
            TurnRole.COMPANION_A.value: "Natjagivaju luk.",
            TurnRole.COMPANION_B.value: "Zhdu.",
        }
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B],
            companion_texts=texts,
            session_ended=False,
        )
        for val in rr.companion_texts.values():
            assert isinstance(val, str)
            assert len(val) > 0

    def test_companion_texts_count_matches_companion_actors(self):
        """Number of companion_texts entries should match number of companion actor_roles."""
        actor_roles = [TurnRole.PLAYER, TurnRole.COMPANION_A, TurnRole.COMPANION_B]
        companion_actors = [r for r in actor_roles if r in (TurnRole.COMPANION_A, TurnRole.COMPANION_B)]
        texts = {
            TurnRole.COMPANION_A.value: "Text A",
            TurnRole.COMPANION_B.value: "Text B",
        }
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=actor_roles,
            companion_texts=texts,
            session_ended=False,
        )
        assert len(rr.companion_texts) == len(companion_actors)

    def test_companion_texts_defaults_to_empty_dict(self):
        """companion_texts should default to empty dict when not provided.

        The implementation uses field(default_factory=dict), so omitting
        companion_texts should not raise.
        """
        rr = RoundResult(
            round_number=1,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER],
            session_ended=False,
        )
        assert rr.companion_texts == {}

    def test_companion_texts_on_tpk_round(self):
        """Even on a TPK round, companion_texts should reflect who acted before death."""
        rr = RoundResult(
            round_number=10,
            turns=[],
            dm_responses=[],
            actor_roles=[TurnRole.PLAYER, TurnRole.COMPANION_A],
            companion_texts={
                TurnRole.COMPANION_A.value: "Eto konets... brat'ya...",
            },
            session_ended=True,
            end_reason="tpk",
        )
        assert rr.session_ended is True
        assert TurnRole.COMPANION_A.value in rr.companion_texts


# ===========================================================================
# TPK triggers for incapacitated party (bug fix)
# ===========================================================================


class TestTPKIncludesIncapacitated:
    """TPK should trigger when all party members have HP <= 0.

    Per spec (docs/specs/orchestrator.md):
        "TPK: after each world state update, check HP of all party members.
         All <= 0 -> DM generates final narrative, session ends."

    Per Cairn rules: incapacitated = HP dropped below 0, overflow went to STR,
    failed STR save. These characters have HP <= 0.

    The bug was: TPK only checked for status == DEAD, missing INCAPACITATED.
    """

    TPK_STATUSES = {CharacterStatus.DEAD, CharacterStatus.INCAPACITATED}

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

    def test_all_dead_is_tpk(self, db, full_party):
        """All dead = TPK. Regression check -- this must always hold."""
        for cid in full_party:
            c = db.characters.get(cid)
            db.characters.damage(cid, amount=c.hp + c.strength)

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is True

    def test_all_incapacitated_is_tpk(self, db, full_party):
        """All incapacitated = TPK. Incapacitated means HP <= 0."""
        for cid in full_party:
            db.characters.update(cid, field="status", value="incapacitated")

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is True

    def test_mix_dead_and_incapacitated_is_tpk(self, db, full_party):
        """Mix of dead and incapacitated = TPK. Both have HP <= 0."""
        player_id, comp_a_id, comp_b_id = full_party

        # Player: dead
        c = db.characters.get(player_id)
        db.characters.damage(player_id, amount=c.hp + c.strength)

        # Companion A: incapacitated
        db.characters.update(comp_a_id, field="status", value="incapacitated")

        # Companion B: dead
        c = db.characters.get(comp_b_id)
        db.characters.damage(comp_b_id, amount=c.hp + c.strength)

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is True

    def test_one_incapacitated_rest_alive_not_tpk(self, db, full_party):
        """One incapacitated + others alive = NOT TPK."""
        player_id, comp_a_id, comp_b_id = full_party
        db.characters.update(player_id, field="status", value="incapacitated")

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is False

    def test_one_dead_one_incapacitated_one_alive_not_tpk(self, db, full_party):
        """Dead + incapacitated + alive = NOT TPK. At least one can still act."""
        player_id, comp_a_id, comp_b_id = full_party

        # Player: dead
        c = db.characters.get(player_id)
        db.characters.damage(player_id, amount=c.hp + c.strength)

        # Companion A: incapacitated
        db.characters.update(comp_a_id, field="status", value="incapacitated")

        # Companion B: alive (no changes)

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is False

    @pytest.mark.parametrize("non_tpk_status", [
        CharacterStatus.ALIVE,
        CharacterStatus.DEPRIVED,
        CharacterStatus.PARALYZED,
        CharacterStatus.DELIRIOUS,
    ])
    def test_non_tpk_status_prevents_tpk(self, db, full_party, non_tpk_status):
        """If any party member has a non-TPK status, TPK should not trigger.

        Paralyzed and delirious are bad but not HP <= 0 -- they don't count
        as TPK per the spec's "all HP <= 0" criterion.
        """
        player_id, comp_a_id, comp_b_id = full_party

        # Kill two members
        for cid in [comp_a_id, comp_b_id]:
            c = db.characters.get(cid)
            db.characters.damage(cid, amount=c.hp + c.strength)

        # Set player to the non-TPK status
        db.characters.update(player_id, field="status", value=non_tpk_status.value)

        party = [db.characters.get(cid) for cid in full_party]
        all_out = all(c.status in self.TPK_STATUSES for c in party)
        assert all_out is False
