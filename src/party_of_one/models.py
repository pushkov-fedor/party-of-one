"""Data models and enums for Party of One.

Matches contracts/models.py — dataclasses with typed enums.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ── Enums ──────────────────────────────────────────────────────────────────


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




# ── Core data models ──────────────────────────────────────────────────────


@dataclass
class InventoryItem:
    name: str
    slots: int = 1
    bulky: bool = False


@dataclass
class Character:
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

    @property
    def occupied_slots(self) -> int:
        return sum(item.slots for item in self.inventory) + self.fatigue

    @property
    def is_alive(self) -> bool:
        return self.status != CharacterStatus.DEAD

    @property
    def can_act(self) -> bool:
        return self.status in (CharacterStatus.ALIVE, CharacterStatus.DEPRIVED)


@dataclass
class Location:
    id: str
    name: str
    description: str
    connected_to: list[str] = field(default_factory=list)
    discovered: bool = False


@dataclass
class Quest:
    id: str
    title: str
    description: str
    status: QuestStatus = QuestStatus.ACTIVE
    giver_character_id: str = ""


@dataclass
class Event:
    id: int
    turn_number: int
    description: str
    event_type: EventType
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Turn:
    id: int
    turn_number: int
    role: TurnRole
    content: str
    commands: list[dict[str, Any]] | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class CompressedHistory:
    id: int
    summary: str
    covers_turns_from: int
    covers_turns_to: int
    created_at: datetime = field(default_factory=datetime.now)


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


# ── Companion profile ─────────────────────────────────────────────────────


@dataclass
class CompanionPersonality:
    traits: list[str]
    goals: list[str]
    fears: list[str]
    speaking_style: str


@dataclass
class CompanionProfile:
    name: str
    class_: str
    personality: CompanionPersonality


# ── Response types ─────────────────────────────────────────────────────────


@dataclass
class DiceResult:
    rolls: list[int]
    total: int


@dataclass
class DamageResult:
    new_hp: int
    new_strength: int | None = None
    requires_scar_roll: bool = False
    requires_str_save: bool = False
    character_died: bool = False


@dataclass
class ToolCallResult:
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None


@dataclass
class DMResponse:
    narrative: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RoundResult:
    round_number: int
    turns: list[Turn]
    dm_responses: list[DMResponse]
    actor_roles: list[TurnRole]  # who acted (player, companion_a, companion_b)
    companion_texts: dict[str, str] = field(default_factory=dict)  # role.value -> first-person text
    session_ended: bool = False
    end_reason: str | None = None
