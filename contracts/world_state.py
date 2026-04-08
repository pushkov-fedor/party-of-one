"""Party of One — API Contract: World State.

Generated from specs in docs/specs/. Do not edit manually.

World State организован по паттерну Repository per aggregate:
5 доменных репозиториев + WorldStateDB как тонкий фасад.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager

from contracts.models import *


# ── Type aliases ───────────────────────────────────────────────────────────

EntityType = Literal["character", "location", "quest"]
CharacterField = Literal["status", "disposition", "location_id", "notes"]
StatName = Literal["strength", "dexterity", "willpower"]
LocationField = Literal["description", "connected_to", "discovered"]


# ── CharacterRepository ───────────────────────────────────────────────────


class CharacterRepository(ABC):
    """CRUD и мутации персонажей: damage, heal, inventory, fatigue, gold."""

    @abstractmethod
    def get(self, character_id: str) -> Character:
        """Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_all(self) -> list[Character]:
        ...

    @abstractmethod
    def list(
        self,
        *,
        location_id: str | None = None,
        role: str | None = None,
    ) -> list[Character]:
        """Filter characters by location and/or role."""
        ...

    @abstractmethod
    def create(
        self,
        *,
        name: str,
        role: Literal["npc", "companion", "player"],
        class_: str,
        description: str,
        disposition: Disposition,
        location_id: str,
        strength: int,
        dexterity: int,
        willpower: int,
        hp: int,
        armor: int = 0,
        gold: int = 0,
    ) -> Character:
        ...

    @abstractmethod
    def damage(self, character_id: str, amount: int) -> DamageResult:
        ...

    @abstractmethod
    def heal(self, character_id: str, amount: int) -> int:
        """Returns new HP."""
        ...

    @abstractmethod
    def damage_stat(
        self, character_id: str, stat: StatName, amount: int,
    ) -> int:
        """Returns new stat value."""
        ...

    @abstractmethod
    def restore_stat(
        self, character_id: str, stat: StatName, amount: int,
    ) -> int:
        """Returns new stat value."""
        ...

    @abstractmethod
    def update(
        self, character_id: str, field: CharacterField, value: str,
    ) -> None:
        ...

    @abstractmethod
    def move(self, character_id: str, location_id: str) -> None:
        """Move to adjacent location. Validates connected_to."""
        ...

    @abstractmethod
    def add_item(
        self, character_id: str, item: str, bulky: bool = False,
    ) -> list[InventoryItem]:
        ...

    @abstractmethod
    def remove_item(
        self, character_id: str, item: str,
    ) -> list[InventoryItem]:
        ...

    @abstractmethod
    def add_fatigue(self, character_id: str) -> int:
        ...

    @abstractmethod
    def remove_fatigue(self, character_id: str) -> int:
        ...

    @abstractmethod
    def update_gold(self, character_id: str, amount: int) -> int:
        ...


# ── LocationRepository ────────────────────────────────────────────────────


class LocationRepository(ABC):
    """CRUD локаций, bidirectional connections."""

    @abstractmethod
    def get(self, location_id: str) -> Location:
        """Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_all(self) -> list[Location]:
        ...

    @abstractmethod
    def create(
        self,
        *,
        name: str,
        description: str,
        connected_to: list[str],
    ) -> Location:
        """connected_to must be non-empty. Connections are bidirectional."""
        ...

    @abstractmethod
    def create_initial(self, name: str, description: str) -> Location:
        """Create the very first location (no connections required)."""
        ...

    @abstractmethod
    def update(
        self, location_id: str, field: LocationField, value: str,
    ) -> None:
        ...


# ── QuestRepository ───────────────────────────────────────────────────────


class QuestRepository(ABC):
    """CRUD квестов, status transitions."""

    @abstractmethod
    def get(self, quest_id: str) -> Quest:
        """Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_all(self) -> list[Quest]:
        ...

    @abstractmethod
    def list(self, status: QuestStatus | None = None) -> list[Quest]:
        """Filter quests by status."""
        ...

    @abstractmethod
    def create(
        self,
        *,
        title: str,
        description: str,
        giver_character_id: str,
    ) -> Quest:
        ...

    @abstractmethod
    def update_status(self, quest_id: str, status: QuestStatus) -> None:
        ...


# ── EventRepository ───────────────────────────────────────────────────────


class EventRepository(ABC):
    """Append-only timeline событий."""

    @abstractmethod
    def add(self, description: str, event_type: EventType) -> Event:
        ...

    @abstractmethod
    def get_recent(self, last_n: int | None = None) -> list[Event]:
        """Oldest first. If last_n — only N most recent."""
        ...


# ── TurnRepository ────────────────────────────────────────────────────────


class TurnRepository(ABC):
    """Сырые ходы и сжатая история."""

    @abstractmethod
    def save_turn(self, turn: Turn) -> None:
        ...

    @abstractmethod
    def get_recent(self, n: int) -> list[Turn]:
        """N most recent turns, oldest first."""
        ...

    @abstractmethod
    def save_compressed_history(self, history: CompressedHistory) -> None:
        ...

    @abstractmethod
    def get_compressed_history(self) -> list[CompressedHistory]:
        """All compressed history summaries, oldest first."""
        ...


# ── WorldStateDB (facade) ─────────────────────────────────────────────────


class WorldStateDB(ABC):
    """Тонкий фасад поверх доменных репозиториев.

    Создаёт соединение с SQLite и передаёт его репозиториям.
    Координирует транзакции, собирает snapshot, предоставляет
    generic entity lookup.
    """

    characters: CharacterRepository
    locations: LocationRepository
    quests: QuestRepository
    events: EventRepository
    turns: TurnRepository

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def transaction(self):
        """Context manager for atomic batch operations."""
        ...

    @abstractmethod
    def get_entity(
        self,
        entity_type: EntityType,
        entity_id: str,
    ) -> Character | Location | Quest:
        """Generic entity lookup. Delegates to the appropriate repository."""
        ...

    @abstractmethod
    def snapshot(self) -> str:
        """Build textual World State snapshot for LLM prompts.

        Determines current location from the player character.
        Aggregates data from multiple repositories.
        """
        ...
