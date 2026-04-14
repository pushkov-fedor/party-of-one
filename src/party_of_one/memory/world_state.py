"""WorldStateDB — thin facade over domain repositories."""

from __future__ import annotations

from typing import Literal

from contracts.world_state import WorldStateDB as WorldStateDBABC

from party_of_one.memory.character_repo import CharacterRepository
from party_of_one.memory.db_session import DBSession
from party_of_one.memory.event_repo import EventRepository
from party_of_one.memory.location_repo import LocationRepository
from party_of_one.memory.quest_repo import QuestRepository
from party_of_one.memory.schema import init_db
from party_of_one.memory.turn_repo import TurnRepository
from party_of_one.models import (
    Character,
    CharacterStatus,
    Location,
    Quest,
    QuestStatus,
)

EntityType = Literal["character", "location", "quest"]


class WorldStateDB(WorldStateDBABC):
    """Facade: creates DB connection, wires repositories, provides
    transaction(), get_entity(), and snapshot().
    """

    def __init__(self, db_path: str = ":memory:"):
        engine = init_db(db_path)
        self._session = DBSession(engine)

        self.characters = CharacterRepository(self._session)
        self.locations = LocationRepository(self._session)
        self.quests = QuestRepository(self._session)
        self.events = EventRepository(self._session)
        self.turns = TurnRepository(self._session)

    def close(self):
        self._session.close()

    def transaction(self):
        return self._session.transaction()

    # ── Generic entity lookup ──────────────────────────────────────────

    def get_entity(
        self, entity_type: EntityType, entity_id: str,
    ) -> Character | Location | Quest:
        if entity_type == "character":
            return self.characters.get(entity_id)
        elif entity_type == "location":
            return self.locations.get(entity_id)
        elif entity_type == "quest":
            return self.quests.get(quest_id=entity_id)
        raise ValueError(f"Unknown entity type: {entity_type}")

    # ── Snapshot ───────────────────────────────────────────────────────

    def snapshot(self) -> str:
        """Build textual world state for LLM prompts."""
        lines = ["## Состояние мира\n"]

        players = self.characters.list(role="player")
        current_loc_id = players[0].location_id if players else ""

        # Текущая локация
        if current_loc_id:
            try:
                loc = self.locations.get(current_loc_id)
                exits = []
                for cid in loc.connected_to:
                    try:
                        c = self.locations.get(cid)
                        exits.append(f"{c.name} [id: {c.id}]")
                    except KeyError:
                        exits.append(cid)
                lines.append(
                    f"Локация: {loc.name} [id: {loc.id}] "
                    f"(выходы: {', '.join(exits)})"
                )
                if loc.description:
                    lines.append(f"  {loc.description}")
                lines.append("")
            except KeyError:
                pass

        # Партия
        party = players + self.characters.list(role="companion")
        if party:
            lines.append("Партия:")
            for c in party:
                inv = ", ".join(
                    f"{i.name} ({i.slots}{', громоздкий' if i.bulky else ''})"
                    for i in c.inventory
                )
                line = (
                    f"- {c.name} [id: {c.id}] ({c.class_}): "
                    f"HP {c.hp}/{c.max_hp}, STR {c.strength}, "
                    f"DEX {c.dexterity}, WIL {c.willpower}, "
                    f"Броня {c.armor}, Золото {c.gold}"
                )
                if c.fatigue > 0:
                    line += f" | Усталость: {c.fatigue}"
                if inv:
                    line += f" | {inv} [{c.occupied_slots}/10 слотов]"
                if c.status != CharacterStatus.ALIVE:
                    line += f" ⚠️ [{c.status.value} — НЕ МОЖЕТ ДЕЙСТВОВАТЬ]"
                elif c.hp == 0:
                    line += f" ⚠️ [HP=0 — БЕЗ СОЗНАНИЯ]"
                lines.append(line)
            lines.append("")

        # Другие персонажи здесь
        if current_loc_id:
            npcs = [
                c for c in self.characters.list(
                    location_id=current_loc_id, role="npc")
                if c.status != CharacterStatus.DEAD
            ]
            if npcs:
                lines.append("Другие персонажи здесь:")
                for c in npcs:
                    disp = f", {c.disposition.value}" if c.disposition else ""
                    lines.append(
                        f"- {c.name} [id: {c.id}] (НПС{disp}): "
                        f"HP {c.hp}/{c.max_hp}, STR {c.strength}, "
                        f"DEX {c.dexterity}, WIL {c.willpower}, "
                        f"Броня {c.armor}"
                    )
                lines.append("")

        # Активные квесты
        active_quests = self.quests.list(status=QuestStatus.ACTIVE)
        if active_quests:
            lines.append("Активные квесты:")
            for q in active_quests:
                lines.append(f"- {q.title} [id: {q.id}]")
            lines.append("")

        # Последние события
        recent_events = self.events.get_recent(last_n=5)
        if recent_events:
            lines.append("Последние события:")
            for e in recent_events:
                lines.append(f"- [{e.event_type.value}] {e.description}")
            lines.append("")

        return "\n".join(lines)
