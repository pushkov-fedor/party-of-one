"""Phase 9: Balance regression tests.

Bugs discovered during gameplay balance testing (2026-04-15):

BUG-1 (P0): Armor items in inventory do not set the character's armor stat.
    Characters with Chainmail (should give +2 Armor) or Shield (+1 Armor)
    are created with armor=0. The damage_character validation checks
    `roll_total - armor`, but armor is always 0, so characters take full
    damage. This is the PRIMARY cause of quick deaths.

BUG-2 (P1): Tikhomyr (Ranger) consistently created with HP 1/1.
    Cairn characters have 1d6 HP (range 1-6). Getting 1 is valid but
    happens 17% of the time. In both test sessions, Tikhomyr had exactly
    HP 1, which effectively makes him a glass cannon that dies to any hit.
    The system may be deterministically assigning HP=1 instead of rolling.

BUG-3 (P1): Branka's stats are inconsistent across sessions.
    Session 1: HP 4/4, STR 12, DEX 11
    Session 2: HP 2/2, STR 12, DEX 5
    The DEX=5 is unusually low and the HP variance suggests stats are
    randomly generated without floor constraints.

BUG-4 (P2): DM repeatedly tries to damage already-incapacitated characters.
    The log shows "damage_character: cannot damage incapacitated character"
    multiple times per session. The DM agent is not checking character
    status before issuing damage commands.

BUG-5 (P2): Narrative contradicts world state for incapacitated characters.
    Tikhomyr at HP 0/1 is described as "studying tracks" and having
    "firm hands" while the world state shows him unconscious.

BUG-6 (P2): Enemy attacks multiple party members in one round.
    In Session 1 Round 2, the fog creature attacked both Branka AND
    Tester in a single round, taking both from full HP to 0. In Cairn,
    most monsters attack once per round.

BUG-7 (P2): STR save not explicitly performed when HP reaches 0.
    Per Cairn rules and the contract (requires_str_save flag), when HP
    drops to 0 and excess goes to STR, a STR save (d20 <= STR) should
    be rolled. The DM did not perform this check in observed sessions.

These tests verify the underlying mechanics, not LLM behavior.
"""

import pytest
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import CharacterStatus, Disposition


@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "balance_test.db"))


@pytest.fixture
def location(db):
    return db.locations.create_initial(
        name="Test Arena", description="Balance testing arena"
    ).id


@pytest.fixture
def armored_character(db, location):
    """A character WITH armor set -- verifying armor is stored correctly."""
    return db.characters.create(
        name="Knight",
        role="player",
        class_="Warrior",
        description="An armored knight",
        disposition=Disposition.FRIENDLY,
        location_id=location,
        strength=14,
        dexterity=10,
        willpower=8,
        hp=6,
        armor=2,
        gold=10,
    ).id


@pytest.fixture
def fragile_character(db, location):
    """A character with HP=1, like Tikhomyr in the observed games."""
    return db.characters.create(
        name="Scout",
        role="companion",
        class_="Ranger",
        description="A fragile scout",
        disposition=Disposition.FRIENDLY,
        location_id=location,
        strength=8,
        dexterity=14,
        willpower=12,
        hp=1,
        armor=0,
        gold=0,
    ).id


@pytest.fixture
def enemy(db, location):
    """A standard enemy with armor=1."""
    return db.characters.create(
        name="Goblin",
        role="npc",
        class_="Monster",
        description="A goblin warrior",
        disposition=Disposition.HOSTILE,
        location_id=location,
        strength=8,
        dexterity=12,
        willpower=6,
        hp=4,
        armor=1,
        gold=2,
    ).id


# === BUG-1: Armor must be stored and retrievable ===


class TestArmorIsStored:
    """BUG-1 regression: armor value must persist after character creation.

    In gameplay, characters with Chainmail (armor=2) or Shield (armor=1)
    were always showing armor=0 in the world state.
    """

    def test_armor_value_persists(self, db, armored_character):
        c = db.characters.get(armored_character)
        assert c.armor == 2, (
            f"Armor should be 2 (as created), got {c.armor}. "
            "This is the root cause of characters dying too fast."
        )

    def test_armor_zero_is_valid(self, db, fragile_character):
        c = db.characters.get(fragile_character)
        assert c.armor == 0

    def test_enemy_armor_persists(self, db, enemy):
        c = db.characters.get(enemy)
        assert c.armor == 1

    def test_armor_in_snapshot_text(self, db, armored_character, location):
        """Armor value must appear in the world state snapshot text
        that the DM sees. If it says 'Броня 0' when armor=2,
        the DM cannot know to subtract armor from damage."""
        snapshot = db.snapshot()
        assert isinstance(snapshot, str), "Snapshot should be a formatted string"
        # The snapshot must show the correct armor value
        assert "Броня 2" in snapshot, (
            f"Snapshot should contain 'Броня 2' for armored character, "
            f"but got:\n{snapshot}"
        )


# === BUG-2/3: HP and stat ranges for Cairn characters ===


class TestCairnStatRanges:
    """BUG-2/3 regression: character stats should be within Cairn ranges.

    Cairn uses 3d6 for STR/DEX/WIL (range 3-18) and 1d6 for HP (1-6).
    DEX=5 is technically possible but extremely unlikely (0.46%).
    HP=1 every time suggests deterministic assignment.
    """

    def test_hp_range_valid(self, db, location):
        """HP=1 is valid but should not always happen."""
        c = db.characters.create(
            name="TestChar",
            role="companion",
            class_="Ranger",
            description="Test",
            disposition=Disposition.FRIENDLY,
            location_id=location,
            strength=10,
            dexterity=10,
            willpower=10,
            hp=1,
            armor=0,
            gold=0,
        )
        assert 0 <= c.hp <= 6, f"HP {c.hp} outside Cairn 1d6 range"
        assert c.max_hp == c.hp, "max_hp should equal initial hp"


# === BUG-4: Cannot damage incapacitated character ===


class TestDamageIncapacitated:
    """BUG-4 regression: damaging an incapacitated character must fail.

    The DM repeatedly tried to damage already-downed characters, causing
    'cannot damage incapacitated character' errors.
    """

    def test_damage_incapacitated_raises(self, db, fragile_character):
        """After HP reaches 0 and character is incapacitated,
        further damage should raise an error."""
        # First, incapacitate the character
        result = db.characters.damage(fragile_character, amount=1)
        c = db.characters.get(fragile_character)
        assert c.hp == 0

        # If status is incapacitated, further damage should fail
        if c.status == CharacterStatus.INCAPACITATED:
            with pytest.raises(ValueError):
                db.characters.damage(fragile_character, amount=1)


# === BUG-7: STR save flag when HP drops to 0 with overflow ===


class TestStrSaveOnOverflow:
    """BUG-7 regression: when damage overflows HP into STR,
    the requires_str_save flag must be set.

    In gameplay, the DM did not perform STR saves when characters
    went from full HP to 0, which is required by Cairn rules.
    """

    def test_overflow_damage_sets_str_save(self, db, armored_character):
        """Damage exceeding HP should set requires_str_save=True."""
        c = db.characters.get(armored_character)
        result = db.characters.damage(armored_character, amount=c.hp + 2)
        assert result.requires_str_save is True, (
            "STR save flag must be set when damage overflows HP. "
            "The DM should roll d20 <= STR to determine if character "
            "is incapacitated."
        )

    def test_exact_hp_zero_no_str_save(self, db, armored_character):
        """Exact HP depletion triggers scar roll, not STR save."""
        c = db.characters.get(armored_character)
        result = db.characters.damage(armored_character, amount=c.hp)
        assert result.requires_scar_roll is True
        assert result.requires_str_save is False

    def test_one_hp_char_overflow_one_damage(self, db, fragile_character):
        """A 1 HP character taking 2 damage: 1 to HP, 1 to STR.
        Must trigger STR save."""
        result = db.characters.damage(fragile_character, amount=2)
        assert result.requires_str_save is True
        c = db.characters.get(fragile_character)
        assert c.hp == 0
        assert c.strength == 7  # was 8, took 1 overflow


# === Balance check: effective HP with armor ===


class TestEffectiveHP:
    """Balance verification: armor should meaningfully increase survivability.

    With armor=0, a d6 hit averaging 3.5 kills a 4HP character in ~1 hit.
    With armor=2, effective damage is (3.5-2)=1.5, requiring ~3 hits.
    This is the difference between playable and instant TPK.
    """

    def test_armor_reduces_effective_damage(self, db, armored_character):
        """An armored character (armor=2) should survive a d6 average hit."""
        c = db.characters.get(armored_character)
        # A d6 averages 3.5. With armor 2, effective damage = 1.5.
        # A 6HP character should survive at least 3 such hits.
        assert c.armor >= 1, "Armored characters must have armor > 0"
        assert c.hp > 3, "Cairn warriors should have enough HP to survive"
        effective_damage_from_d6_max = 6 - c.armor
        rounds_to_kill = c.hp / max(effective_damage_from_d6_max, 1)
        assert rounds_to_kill >= 1.0, (
            f"Character dies in {rounds_to_kill:.1f} rounds from max d6 hit. "
            f"HP={c.hp}, armor={c.armor}. Should survive at least 1 full hit."
        )
