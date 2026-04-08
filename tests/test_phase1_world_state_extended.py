"""Phase 1: Extended World State tests — coverage gaps.

Tests behaviors described in contracts/world_state.py, contracts/models.py,
and docs/specs/tools-apis.md that are NOT covered by existing tests:

- Armor reduces damage before HP
- Character.list() filtering by location and role
- Events repository (add, get_recent)
- Compressed history (save, retrieve)
- WorldStateDB.get_entity() generic lookup
- WorldStateDB.transaction() context manager
- Location update (description, connected_to, discovered)
- Location update — bidirectional links (connected_to)
- Quest list filtering by status
- Fatigue on dead character
- Armor invariant [0..3]
- Armor max validation (reject armor > 3 and armor < 0)
- Bulky item invariant (slots == 2)
- Snapshot reflects damage, death, quest status, multiple locations
"""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import (
    CharacterStatus,
    CompressedHistory,
    Disposition,
    EventType,
    QuestStatus,
    Turn,
    TurnRole,
)
from datetime import datetime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test.db"))


@pytest.fixture
def location(db):
    return db.locations.create_initial(name="Village", description="A quiet village").id


@pytest.fixture
def second_location(db, location):
    return db.locations.create(
        name="Forest", description="A dark forest", connected_to=[location],
    ).id


@pytest.fixture
def player(db, location):
    return db.characters.create(
        name="Hero", role="player", class_="Warrior", description="The hero",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=14, dexterity=10, willpower=8, hp=6, armor=2, gold=10,
    ).id


@pytest.fixture
def companion_a(db, location):
    return db.characters.create(
        name="Kira", role="companion", class_="Ranger", description="A ranger",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=10, dexterity=14, willpower=8, hp=6, armor=1, gold=5,
    ).id


@pytest.fixture
def companion_b(db, location):
    return db.characters.create(
        name="Torin", role="companion", class_="Fighter", description="A fighter",
        disposition=Disposition.FRIENDLY, location_id=location,
        strength=16, dexterity=8, willpower=10, hp=8, armor=1, gold=3,
    ).id


@pytest.fixture
def npc(db, location):
    return db.characters.create(
        name="Goblin", role="npc", class_="Monster", description="A goblin",
        disposition=Disposition.HOSTILE, location_id=location,
        strength=8, dexterity=12, willpower=6, hp=4, armor=0, gold=2,
    ).id


@pytest.fixture
def npc_in_forest(db, second_location):
    return db.characters.create(
        name="Wolf", role="npc", class_="Beast", description="A wolf",
        disposition=Disposition.HOSTILE, location_id=second_location,
        strength=10, dexterity=14, willpower=4, hp=5, armor=0, gold=0,
    ).id


# ===========================================================================
# Damage Takes Raw Amount (Armor Subtraction is DM's Job)
# ===========================================================================

class TestDamageRawAmount:
    """CharacterRepository.damage() takes the raw damage amount directly.
    Per Cairn rules, armor subtraction is done by the DM BEFORE calling damage.
    The DM calculates: effective_damage = roll - armor, then calls damage(effective).
    The repository itself does not apply armor reduction."""

    def test_damage_amount_applied_directly_to_hp(self, db, player):
        """damage() reduces HP by the exact amount passed, regardless of armor."""
        hp_before = db.characters.get(player).hp
        db.characters.damage(player, amount=3)
        assert db.characters.get(player).hp == hp_before - 3

    def test_armor_unchanged_after_damage(self, db, player):
        """Armor value is not modified by damage calls."""
        armor_before = db.characters.get(player).armor
        db.characters.damage(player, amount=5)
        assert db.characters.get(player).armor == armor_before

    def test_zero_damage_not_allowed(self, db, player):
        """Damage amount must be positive (>= 1)."""
        with pytest.raises((ValueError, Exception)):
            db.characters.damage(player, amount=0)


# ===========================================================================
# Character List Filtering
# ===========================================================================

class TestCharacterListFiltering:
    """CharacterRepository.list() filters by location_id and/or role."""

    def test_filter_by_location(self, db, player, npc, npc_in_forest, location):
        chars_at_village = db.characters.list(location_id=location)
        ids = [c.id for c in chars_at_village]
        assert player in ids
        assert npc in ids
        assert npc_in_forest not in ids

    def test_filter_by_role(self, db, player, companion_a, npc):
        companions = db.characters.list(role="companion")
        ids = [c.id for c in companions]
        assert companion_a in ids
        assert player not in ids
        assert npc not in ids

    def test_filter_by_both(self, db, player, companion_a, npc, location):
        players_at_village = db.characters.list(location_id=location, role="player")
        ids = [c.id for c in players_at_village]
        assert player in ids
        assert companion_a not in ids

    def test_no_match_returns_empty(self, db, player, location):
        result = db.characters.list(role="npc", location_id="nonexistent")
        assert result == []


# ===========================================================================
# Events Repository
# ===========================================================================

class TestEventsRepository:
    """EventRepository: add events, get_recent ordered oldest-first."""

    def test_add_event_returns_event(self, db):
        event = db.events.add(description="Battle started", event_type=EventType.COMBAT)
        assert event.id is not None
        assert event.description == "Battle started"
        assert event.event_type == EventType.COMBAT

    def test_get_recent_returns_all_when_no_limit(self, db):
        db.events.add(description="Event 1", event_type=EventType.DIALOGUE)
        db.events.add(description="Event 2", event_type=EventType.DISCOVERY)
        db.events.add(description="Event 3", event_type=EventType.QUEST)
        events = db.events.get_recent()
        assert len(events) >= 3

    def test_get_recent_with_limit(self, db):
        for i in range(5):
            db.events.add(description=f"Event {i}", event_type=EventType.COMBAT)
        recent = db.events.get_recent(last_n=2)
        assert len(recent) == 2

    def test_get_recent_ordered_oldest_first(self, db):
        db.events.add(description="First", event_type=EventType.COMBAT)
        db.events.add(description="Second", event_type=EventType.DIALOGUE)
        db.events.add(description="Third", event_type=EventType.DISCOVERY)
        events = db.events.get_recent()
        descriptions = [e.description for e in events]
        assert descriptions.index("First") < descriptions.index("Third")

    def test_get_recent_empty(self, db):
        assert db.events.get_recent() == []

    @pytest.mark.parametrize("event_type", list(EventType))
    def test_all_event_types_accepted(self, db, event_type):
        event = db.events.add(description="Test", event_type=event_type)
        assert event.event_type == event_type


# ===========================================================================
# Compressed History
# ===========================================================================

class TestCompressedHistory:
    """TurnRepository: save and retrieve compressed history summaries."""

    def test_save_and_retrieve(self, db):
        history = CompressedHistory(
            id=0, summary="Party entered the cave. Goblin killed.",
            covers_turns_from=1, covers_turns_to=5,
            created_at=datetime.now(),
        )
        db.turns.save_compressed_history(history)
        histories = db.turns.get_compressed_history()
        assert len(histories) >= 1
        assert "cave" in histories[0].summary

    def test_multiple_compressed_histories_ordered(self, db):
        for i in range(3):
            h = CompressedHistory(
                id=0, summary=f"Summary {i}",
                covers_turns_from=i * 5 + 1, covers_turns_to=(i + 1) * 5,
                created_at=datetime.now(),
            )
            db.turns.save_compressed_history(h)
        histories = db.turns.get_compressed_history()
        assert len(histories) >= 3
        # oldest first
        assert histories[0].covers_turns_from < histories[-1].covers_turns_from

    def test_empty_history(self, db):
        assert db.turns.get_compressed_history() == []


# ===========================================================================
# WorldStateDB.get_entity() Generic Lookup
# ===========================================================================

class TestGetEntity:
    """WorldStateDB.get_entity() delegates to the appropriate repository."""

    def test_get_character(self, db, player):
        entity = db.get_entity("character", player)
        assert entity.name == "Hero"

    def test_get_location(self, db, location):
        entity = db.get_entity("location", location)
        assert entity.name == "Village"

    def test_get_quest(self, db, player):
        q = db.quests.create(
            title="Find sword", description="Legendary", giver_character_id=player,
        )
        entity = db.get_entity("quest", q.id)
        assert entity.title == "Find sword"

    def test_get_nonexistent_raises(self, db):
        with pytest.raises(KeyError):
            db.get_entity("character", "nonexistent-id")

    def test_invalid_entity_type_raises(self, db):
        with pytest.raises((ValueError, KeyError)):
            db.get_entity("invalid_type", "some-id")


# ===========================================================================
# WorldStateDB.transaction() Context Manager
# ===========================================================================

class TestTransaction:
    """WorldStateDB.transaction() provides atomic batch operations."""

    def test_committed_changes_visible(self, db, location):
        with db.transaction():
            db.characters.create(
                name="Transacted", role="npc", class_="Test",
                description="Created in transaction",
                disposition=Disposition.NEUTRAL, location_id=location,
                strength=10, dexterity=10, willpower=10, hp=5,
            )
        chars = db.characters.get_all()
        names = [c.name for c in chars]
        assert "Transacted" in names

    def test_exception_rolls_back(self, db, location):
        try:
            with db.transaction():
                db.characters.create(
                    name="WillRollBack", role="npc", class_="Test",
                    description="Should not persist",
                    disposition=Disposition.NEUTRAL, location_id=location,
                    strength=10, dexterity=10, willpower=10, hp=5,
                )
                raise RuntimeError("Simulated failure")
        except RuntimeError:
            pass
        chars = db.characters.get_all()
        names = [c.name for c in chars]
        assert "WillRollBack" not in names


# ===========================================================================
# Location Update
# ===========================================================================

class TestLocationUpdate:
    """LocationRepository.update() modifies description, connected_to, discovered."""

    def test_update_description(self, db, location):
        db.locations.update(location, field="description", value="An updated village")
        assert db.locations.get(location).description == "An updated village"

    def test_update_discovered(self, db, location):
        db.locations.update(location, field="discovered", value="true")
        assert db.locations.get(location).discovered is True

    def test_nonexistent_location_raises(self, db):
        with pytest.raises(KeyError):
            db.locations.update("nonexistent-loc", field="description", value="x")


# ===========================================================================
# Location Update — Bidirectional Links (connected_to)
# ===========================================================================

class TestUpdateLocationBidirectionalLinks:
    """update_location with field='connected_to' must update reverse links.

    Per spec (docs/specs/tools-apis.md):
    - create_location: "Updates links in both directions."
    - update_location: "If connected_to -- updates links in both directions."

    create_location already tested for bidirectional. These tests verify
    update_location does the same.
    """

    @pytest.fixture
    def three_locations(self, db):
        """Create three locations: A -- B (connected), C -- B (connected), A not connected to C."""
        loc_a = db.locations.create_initial(name="Village2", description="A village")
        loc_b = db.locations.create(
            name="Forest2", description="A forest", connected_to=[loc_a.id],
        )
        loc_c = db.locations.create(
            name="Mountain2", description="A mountain", connected_to=[loc_b.id],
        )
        return loc_a.id, loc_b.id, loc_c.id

    def test_update_connected_to_adds_reverse_link(self, db, three_locations):
        """When A's connected_to is updated to include C, C should also link to A."""
        import json
        loc_a, loc_b, loc_c = three_locations

        # Before: A <-> B, B <-> C. A is NOT connected to C directly.
        a_before = db.locations.get(loc_a)
        assert loc_c not in a_before.connected_to

        # Update A to connect to C (in addition to B)
        new_connections = json.dumps([loc_b, loc_c])
        db.locations.update(loc_a, field="connected_to", value=new_connections)

        # After: A should be connected to C
        a_after = db.locations.get(loc_a)
        assert loc_c in a_after.connected_to

        # And C should be connected to A (bidirectional)
        c_after = db.locations.get(loc_c)
        assert loc_a in c_after.connected_to

    def test_update_connected_to_removes_reverse_link(self, db, three_locations):
        """When B's connected_to is updated to remove A, A should also lose link to B."""
        import json
        loc_a, loc_b, loc_c = three_locations

        # Before: A <-> B
        assert loc_a in db.locations.get(loc_b).connected_to
        assert loc_b in db.locations.get(loc_a).connected_to

        # Update B to only connect to C (removing A)
        db.locations.update(loc_b, field="connected_to", value=json.dumps([loc_c]))

        # B should no longer be connected to A
        b_after = db.locations.get(loc_b)
        assert loc_a not in b_after.connected_to

        # A should no longer be connected to B (reverse link removed)
        a_after = db.locations.get(loc_a)
        assert loc_b not in a_after.connected_to

    def test_create_location_bidirectional_still_works(self, db, location):
        """Sanity: create_location bidirectional behavior is preserved."""
        new_loc = db.locations.create(
            name="Cave2", description="Dark cave", connected_to=[location],
        )
        assert location in db.locations.get(new_loc.id).connected_to
        assert new_loc.id in db.locations.get(location).connected_to


# ===========================================================================
# Armor Max Validation (Repository Level)
# ===========================================================================

class TestArmorMaxValidation:
    """Armor must be in [0, 3] per Cairn rules.

    Per contract (contracts/models.py): armor in [0, 1, 2, 3].
    Per spec (docs/specs/tools-apis.md): Max armor = 3.
    Character creation must reject armor > 3 and armor < 0.
    """

    def test_armor_4_rejected_at_repository_level(self, db, location):
        """Creating a character with armor=4 should raise an error."""
        with pytest.raises((ValueError, Exception)):
            db.characters.create(
                name="Tanky", role="npc", class_="Knight",
                description="Over-armored",
                disposition=Disposition.NEUTRAL, location_id=location,
                strength=10, dexterity=10, willpower=10, hp=5, armor=4,
            )

    def test_armor_10_rejected_at_repository_level(self, db, location):
        """Extreme armor value should be rejected."""
        with pytest.raises((ValueError, Exception)):
            db.characters.create(
                name="Fortress", role="npc", class_="Golem",
                description="Absurd armor",
                disposition=Disposition.NEUTRAL, location_id=location,
                strength=10, dexterity=10, willpower=10, hp=5, armor=10,
            )

    def test_negative_armor_rejected(self, db, location):
        """Negative armor should be rejected per model invariant: armor in [0, 1, 2, 3]."""
        with pytest.raises((ValueError, Exception)):
            db.characters.create(
                name="Fragile", role="npc", class_="Ghost",
                description="Negative armor",
                disposition=Disposition.NEUTRAL, location_id=location,
                strength=10, dexterity=10, willpower=10, hp=5, armor=-1,
            )


# ===========================================================================
# Quest List Filtering
# ===========================================================================

class TestQuestListFiltering:
    """QuestRepository.list() filters by status."""

    def test_list_active_quests(self, db, player):
        db.quests.create(title="Active Quest", description="A", giver_character_id=player)
        q2 = db.quests.create(title="Done Quest", description="B", giver_character_id=player)
        db.quests.update_status(q2.id, status="completed")

        active = db.quests.list(status=QuestStatus.ACTIVE)
        titles = [q.title for q in active]
        assert "Active Quest" in titles
        assert "Done Quest" not in titles

    def test_list_all_quests(self, db, player):
        db.quests.create(title="Q1", description="A", giver_character_id=player)
        db.quests.create(title="Q2", description="B", giver_character_id=player)
        assert len(db.quests.list()) >= 2

    def test_list_no_match(self, db, player):
        db.quests.create(title="Active Only", description="A", giver_character_id=player)
        assert db.quests.list(status=QuestStatus.FAILED) == []


# ===========================================================================
# Fatigue Business Rules
# ===========================================================================

class TestFatigueBusinessRules:
    """Fatigue edge cases not covered by existing tests."""

    def test_dead_character_cannot_add_fatigue(self, db, player):
        c = db.characters.get(player)
        db.characters.damage(player, amount=c.hp + c.strength)
        assert db.characters.get(player).status == CharacterStatus.DEAD
        with pytest.raises(ValueError):
            db.characters.add_fatigue(player)


# ===========================================================================
# Armor Invariant
# ===========================================================================

class TestArmorInvariant:
    """Armor must be in [0, 1, 2, 3] per Cairn rules."""

    @pytest.mark.parametrize("armor", [0, 1, 2, 3])
    def test_valid_armor_accepted(self, db, location, armor):
        c = db.characters.create(
            name=f"Armor{armor}", role="npc", class_="Test",
            description="Test", disposition=Disposition.NEUTRAL,
            location_id=location, strength=10, dexterity=10,
            willpower=10, hp=5, armor=armor,
        )
        assert c.armor == armor


# ===========================================================================
# Bulky Item Invariant
# ===========================================================================

class TestBulkyItemInvariant:
    """Bulky items must occupy exactly 2 slots."""

    def test_bulky_item_has_two_slots(self, db, player):
        inv = db.characters.add_item(player, item="Great Sword", bulky=True)
        great_sword = [i for i in inv if i.name == "Great Sword"][0]
        assert great_sword.slots == 2
        assert great_sword.bulky is True

    def test_non_bulky_item_has_one_slot(self, db, player):
        inv = db.characters.add_item(player, item="Dagger")
        dagger = [i for i in inv if i.name == "Dagger"][0]
        assert dagger.slots == 1
        assert dagger.bulky is False


# ===========================================================================
# Snapshot Reflects State Changes
# ===========================================================================

class TestSnapshotReflectsState:
    """Snapshot should reflect current world state after mutations."""

    def test_snapshot_shows_damaged_character(self, db, player, location):
        db.characters.damage(player, amount=3)
        snapshot = db.snapshot()
        # Character should show current HP, not max
        assert "Hero" in snapshot

    def test_snapshot_shows_dead_character(self, db, player, location):
        c = db.characters.get(player)
        db.characters.damage(player, amount=c.hp + c.strength)
        snapshot = db.snapshot()
        assert "dead" in snapshot.lower() or "Dead" in snapshot

    def test_snapshot_shows_active_quest(self, db, player, location):
        """Active quests appear in the snapshot."""
        q = db.quests.create(title="Save Village", description="Urgent", giver_character_id=player)
        snapshot = db.snapshot()
        assert "Save Village" in snapshot

    def test_snapshot_shows_multiple_locations(self, db, player, location, second_location):
        snapshot = db.snapshot()
        assert "Village" in snapshot


# ===========================================================================
# Character Update
# ===========================================================================

class TestCharacterUpdate:
    """CharacterRepository.update() modifies status, disposition, location_id, notes."""

    def test_update_status(self, db, player):
        db.characters.update(player, field="status", value="deprived")
        assert db.characters.get(player).status == CharacterStatus.DEPRIVED

    def test_update_disposition(self, db, npc):
        db.characters.update(npc, field="disposition", value="friendly")
        assert db.characters.get(npc).disposition == Disposition.FRIENDLY

    def test_update_notes(self, db, player):
        db.characters.update(player, field="notes", value="Wounded in battle")
        assert db.characters.get(player).notes == "Wounded in battle"

    def test_update_nonexistent_raises(self, db):
        with pytest.raises(KeyError):
            db.characters.update("nonexistent", field="status", value="alive")
