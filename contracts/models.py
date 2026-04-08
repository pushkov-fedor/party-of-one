"""Party of One — API Contract: Data Models.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

class CharacterStatus(str, enum.Enum):
    ALIVE = "alive"
    DEAD = "dead"
    INCAPACITATED = "incapacitated"
    DEPRIVED = "deprived"
    PARALYZED = "paralyzed"
    DELIRIOUS = "delirious"


class Disposition(str, enum.Enum):
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"


class CharacterRole(str, enum.Enum):
    PLAYER = "player"
    COMPANION = "companion"
    NPC = "npc"


class QuestStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, enum.Enum):
    COMBAT = "combat"
    DIALOGUE = "dialogue"
    DISCOVERY = "discovery"
    QUEST = "quest"
    DEATH = "death"


class TurnRole(str, enum.Enum):
    PLAYER = "player"
    DM = "dm"
    COMPANION_A = "companion_a"
    COMPANION_B = "companion_b"


class SessionState(str, enum.Enum):
    AWAITING_PLAYER = "awaiting_player"
    PROCESSING = "processing"
    SESSION_ENDED = "session_ended"


# ── Core data models ──


@dataclass
class InventoryItem:
    """A single item in a character's inventory.

    Invariants:
        - slots >= 1
        - bulky == True implies slots == 2
    """

    name: str
    slots: int = 1
    bulky: bool = False


@dataclass
class Character:
    """Any entity in the world: player, companion, NPC, or enemy.

    Invariants:
        - hp <= max_hp
        - strength <= max_strength
        - dexterity <= max_dexterity
        - willpower <= max_willpower
        - fatigue >= 0
        - armor in [0, 1, 2, 3]
        - gold >= 0
        - occupied_slots = sum(item.slots for item in inventory) + fatigue
        - occupied_slots > 10 is not allowed
    """

    id: str
    name: str
    class_: str
    role: CharacterRole
    strength: int
    dexterity: int
    willpower: int
    max_strength: int
    max_dexterity: int
    max_willpower: int
    hp: int
    max_hp: int
    armor: int = 0
    gold: int = 0
    inventory: list[InventoryItem] = field(default_factory=list)
    fatigue: int = 0
    status: CharacterStatus = CharacterStatus.ALIVE
    location_id: str = ""
    description: str = ""
    disposition: Disposition = Disposition.NEUTRAL
    notes: str = ""


@dataclass
class Location:
    """A named place in the game world.

    Invariants:
        - connected_to references existing location IDs
    """

    id: str
    name: str
    description: str
    connected_to: list[str] = field(default_factory=list)
    discovered: bool = False


@dataclass
class Quest:
    """A quest tracked by the world state."""

    id: str
    title: str
    description: str
    status: QuestStatus = QuestStatus.ACTIVE
    giver_character_id: str = ""


@dataclass
class Event:
    """A recorded event in the game timeline."""

    id: int
    turn_number: int
    description: str
    event_type: EventType
    created_at: datetime


@dataclass
class Turn:
    """A raw turn record, used for session recovery and context building.

    Invariants:
        - role is one of TurnRole values
    """

    id: int
    turn_number: int
    role: TurnRole
    content: str
    commands: list[dict[str, Any]] | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CompressedHistory:
    """A summary covering a range of turns, produced by the compressor."""

    id: int
    summary: str
    covers_turns_from: int
    covers_turns_to: int
    created_at: datetime


@dataclass
class Session:
    """Top-level session state."""

    session_id: str
    campaign_id: str
    created_at: datetime
    last_active: datetime
    turn_count: int
    round_count: int
    state: SessionState
    party: list[Character]
    active_scene: str


# ── Companion profile (loaded from YAML) ──


@dataclass
class CompanionPersonality:
    traits: list[str]
    goals: list[str]
    fears: list[str]
    speaking_style: str


@dataclass
class CompanionProfile:
    """Pre-configured companion template loaded from data/companions.yaml.

    Stats (STR/DEX/WIL/HP) are NOT part of the profile -- they are
    rolled via roll_dice at game init time per Cairn rules.
    """

    name: str
    class_: str
    personality: CompanionPersonality


# ── Companion structured response ──



# ── DM tool-call result helpers ──


@dataclass
class DiceResult:
    """Result of a roll_dice call."""

    rolls: list[int]
    total: int


@dataclass
class DamageResult:
    """Result of a damage_character call, with flags for follow-up rolls."""

    new_hp: int
    new_strength: int | None = None
    requires_scar_roll: bool = False
    requires_str_save: bool = False
    character_died: bool = False


@dataclass
class ToolCallResult:
    """Generic wrapper for the outcome of executing a single DM tool call."""

    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
