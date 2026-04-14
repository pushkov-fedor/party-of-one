"""ToolExecutor — validates and executes DM tool calls against WorldStateDB."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from contracts.tools import ToolExecutor as ToolExecutorABC

from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import Disposition, ToolCallResult
from party_of_one.rag.retriever import Retriever
from party_of_one.tools.tool_definitions import TOOL_DEFINITIONS  # re-export


class ToolExecutor(ToolExecutorABC):
    """Validates and executes DM tool calls against WorldStateDB."""

    MAX_COMMANDS_PER_TURN = 10
    MAX_DAMAGE_PER_CALL = 50

    def __init__(self, db: WorldStateDB, retriever: Retriever | None = None):
        self.db = db
        self._retriever = retriever
        self._handlers: dict[str, Any] = {
            "roll_dice": self._roll_dice,
            "get_entity": self._get_entity,
            "damage_character": self._damage_character,
            "heal_character": self._heal_character,
            "damage_stat": self._damage_stat,
            "restore_stat": self._restore_stat,
            "update_character": self._update_character,
            "move_entity": self._move_entity,
            "add_item": self._add_item,
            "remove_item": self._remove_item,
            "add_fatigue": self._add_fatigue,
            "remove_fatigue": self._remove_fatigue,
            "update_gold": self._update_gold,
            "add_event": self._add_event,
            "update_quest": self._update_quest,
            "update_location": self._update_location,
            "create_character": self._create_character,
            "create_quest": self._create_quest,
            "create_location": self._create_location,
            "search_rules": self._search_rules,
        }

    def execute(self, tool_name: str, params: dict[str, Any]) -> ToolCallResult:
        handler = self._handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")
        try:
            result = handler(**params)
            return ToolCallResult(tool_name=tool_name, success=True, result=result)
        except (ValueError, KeyError) as e:
            return ToolCallResult(tool_name=tool_name, success=False, error=str(e))

    def execute_batch(self, calls: list[dict[str, Any]]) -> list[ToolCallResult]:
        if len(calls) > self.MAX_COMMANDS_PER_TURN:
            raise ValueError(f"Too many commands: {len(calls)} > {self.MAX_COMMANDS_PER_TURN}")
        results = []
        with self.db.transaction():
            for call in calls:
                name = call["name"]
                params = call.get("params", call.get("args", {}))
                handler = self._handlers.get(name)
                if not handler:
                    raise ValueError(f"Unknown tool: {name}")
                result = handler(**params)
                results.append(ToolCallResult(tool_name=name, success=True, result=result))
        return results

    # ── Handlers ───────────────────────────────────────────────────────

    def _roll_dice(self, sides: int, count: int = 1) -> dict:
        from party_of_one.tools.dice import roll_dice
        r = roll_dice(sides, count)
        return {"rolls": r.rolls, "total": r.total}

    def _get_entity(self, type: str, id: str) -> dict:
        entity = self.db.get_entity(type, id)
        return asdict(entity)

    def _damage_character(self, character_id: str, amount: int) -> dict:
        if amount > self.MAX_DAMAGE_PER_CALL:
            raise ValueError(f"Damage {amount} exceeds max {self.MAX_DAMAGE_PER_CALL}")
        result = self.db.characters.damage(character_id, amount)
        return asdict(result)

    def _heal_character(self, character_id: str, amount: int) -> dict:
        new_hp = self.db.characters.heal(character_id, amount)
        return {"character_id": character_id, "hp": new_hp}

    def _damage_stat(self, character_id: str, stat: str, amount: int) -> dict:
        new_val = self.db.characters.damage_stat(character_id, stat, amount)
        return {"character_id": character_id, stat: new_val}

    def _restore_stat(self, character_id: str, stat: str, amount: int) -> dict:
        new_val = self.db.characters.restore_stat(character_id, stat, amount)
        return {"character_id": character_id, stat: new_val}

    def _update_character(self, character_id: str, field: str, value: str) -> dict:
        self.db.characters.update(character_id, field, value)
        return {"character_id": character_id, field: value}

    def _move_entity(self, entity_id: str, location_id: str) -> dict:
        self.db.characters.move(entity_id, location_id)
        return {"entity_id": entity_id, "location_id": location_id}

    def _add_item(self, character_id: str, item: str, bulky: bool = False) -> dict:
        inv = self.db.characters.add_item(character_id, item, bulky=bulky)
        return {"character_id": character_id, "item": item, "inventory_count": len(inv)}

    def _remove_item(self, character_id: str, item: str) -> dict:
        inv = self.db.characters.remove_item(character_id, item)
        return {"character_id": character_id, "removed": item, "inventory_count": len(inv)}

    def _add_fatigue(self, character_id: str) -> dict:
        f = self.db.characters.add_fatigue(character_id)
        return {"character_id": character_id, "fatigue": f}

    def _remove_fatigue(self, character_id: str) -> dict:
        f = self.db.characters.remove_fatigue(character_id)
        return {"character_id": character_id, "fatigue": f}

    def _update_gold(self, character_id: str, amount: int) -> dict:
        g = self.db.characters.update_gold(character_id, amount)
        return {"character_id": character_id, "gold": g}

    def _add_event(self, description: str, event_type: str) -> dict:
        e = self.db.events.add(description, event_type)
        return {"event_id": e.id, "event_type": e.event_type.value}

    def _update_quest(self, quest_id: str, status: str) -> dict:
        self.db.quests.update_status(quest_id, status)
        return {"quest_id": quest_id, "status": status}

    def _update_location(self, location_id: str, field: str, value: str) -> dict:
        self.db.locations.update(location_id, field, value)
        return {"location_id": location_id, field: value}

    def _create_character(self, **kwargs) -> dict:
        if "disposition" in kwargs and isinstance(kwargs["disposition"], str):
            kwargs["disposition"] = Disposition(kwargs["disposition"])
        # Prevent duplicate creation — return existing if name matches
        name = kwargs.get("name", "")
        if name:
            existing = self.db.characters.get_all()
            for c in existing:
                if c.name == name:
                    return {
                        "error": f"Персонаж '{name}' уже существует",
                        "character_id": c.id,
                        "name": c.name,
                    }
        char = self.db.characters.create(**kwargs)
        return {"character_id": char.id, "name": char.name}

    def _create_quest(self, title: str, description: str, giver_character_id: str) -> dict:
        q = self.db.quests.create(title=title, description=description,
                                   giver_character_id=giver_character_id)
        return {"quest_id": q.id, "title": q.title}

    def _create_location(self, name: str, description: str, connected_to: list[str]) -> dict:
        loc = self.db.locations.create(name=name, description=description,
                                        connected_to=connected_to)
        return {"location_id": loc.id, "name": loc.name}

    def _search_rules(self, query: str) -> dict:
        if not self._retriever:
            return {"chunks": [], "query": query}
        result = self._retriever.search(query)
        return {
            "query": result.query,
            "chunks": [
                {"text": c.text, "section": c.section, "subsection": c.subsection}
                for c in result.chunks
            ],
        }
