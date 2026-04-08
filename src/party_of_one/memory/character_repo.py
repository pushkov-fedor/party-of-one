"""CharacterRepository — CRUD, damage, heal, inventory, fatigue, gold."""

from __future__ import annotations

import json
import uuid
from typing import Literal

from sqlalchemy import select, update, insert

from contracts.world_state import CharacterRepository as CharacterRepositoryABC

from party_of_one.memory.db_session import DBSession
from party_of_one.memory.schema import characters, locations
from party_of_one.models import (
    Character,
    CharacterRole,
    CharacterStatus,
    DamageResult,
    Disposition,
    InventoryItem,
)

StatName = Literal["strength", "dexterity", "willpower"]
CharacterField = Literal["status", "disposition", "location_id", "notes"]


class CharacterRepository(CharacterRepositoryABC):
    def __init__(self, session: DBSession):
        self._s = session

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, character_id: str) -> Character:
        row = self._s.conn.execute(
            select(characters).where(characters.c.id == character_id)
        ).mappings().fetchone()
        if not row:
            raise KeyError(f"Character '{character_id}' not found")
        return self._to_model(row)

    def get_all(self) -> list[Character]:
        rows = self._s.conn.execute(select(characters)).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    def list(
        self, *, location_id: str | None = None, role: str | None = None,
    ) -> list[Character]:
        stmt = select(characters)
        if location_id is not None:
            stmt = stmt.where(characters.c.location_id == location_id)
        if role is not None:
            stmt = stmt.where(characters.c.role == role)
        rows = self._s.conn.execute(stmt).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    # ── Create ─────────────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        role: Literal["npc", "companion", "player"],
        class_: str,
        strength: int,
        dexterity: int,
        willpower: int,
        hp: int,
        description: str = "",
        disposition: Disposition = Disposition.NEUTRAL,
        location_id: str = "",
        armor: int = 0,
        gold: int = 0,
    ) -> Character:
        if armor < 0 or armor > 3:
            raise ValueError(f"Armor {armor} exceeds max 3")
        if location_id:
            self._ensure_location(location_id)
        char_id = f"{role}_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        disp_val = disposition.value if isinstance(disposition, Disposition) else disposition
        self._s.conn.execute(insert(characters).values(
            id=char_id, name=name, class_=class_, role=role,
            strength=strength, dexterity=dexterity, willpower=willpower,
            max_strength=strength, max_dexterity=dexterity, max_willpower=willpower,
            hp=hp, max_hp=hp, armor=armor, gold=gold,
            location_id=location_id, description=description, disposition=disp_val,
        ))
        self._s.auto_commit()
        return self.get(char_id)

    # ── Damage / Heal ──────────────────────────────────────────────────

    def damage(self, character_id: str, amount: int) -> DamageResult:
        if amount < 1:
            raise ValueError("amount must be >= 1")
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Character '{character_id}' is dead")

        new_hp = char.hp - amount
        if new_hp > 0:
            self._set(character_id, hp=new_hp)
            self._s.auto_commit()
            return DamageResult(new_hp=new_hp)
        if new_hp == 0:
            self._set(character_id, hp=0)
            self._s.auto_commit()
            return DamageResult(new_hp=0, requires_scar_roll=True)
        # HP < 0 → overflow to STR
        self._set(character_id, hp=0)
        overflow = abs(new_hp)
        new_str = char.strength - overflow
        if new_str <= 0:
            self._set(character_id, strength=0, status=CharacterStatus.DEAD.value)
            self._s.auto_commit()
            return DamageResult(new_hp=0, new_strength=0, character_died=True)
        self._set(character_id, strength=new_str)
        self._s.auto_commit()
        return DamageResult(new_hp=0, new_strength=new_str, requires_str_save=True)

    def heal(self, character_id: str, amount: int) -> int:
        if amount < 1:
            raise ValueError("amount must be >= 1")
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Character '{character_id}' is dead")
        if char.status == CharacterStatus.DEPRIVED:
            raise ValueError(f"Character '{character_id}' is deprived — cannot heal")
        new_hp = min(char.hp + amount, char.max_hp)
        self._set(character_id, hp=new_hp)
        self._s.auto_commit()
        return new_hp

    # ── Stat damage / restore ──────────────────────────────────────────

    def damage_stat(self, character_id: str, stat: StatName, amount: int) -> int:
        if stat not in ("strength", "dexterity", "willpower"):
            raise ValueError(f"Invalid stat: {stat}")
        if amount < 1:
            raise ValueError("amount must be >= 1")
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Character '{character_id}' is dead")
        new_val = max(0, getattr(char, stat) - amount)
        updates = {stat: new_val}
        if new_val <= 0:
            status_map = {"strength": "dead", "dexterity": "paralyzed", "willpower": "delirious"}
            updates["status"] = status_map[stat]
        self._set(character_id, **updates)
        self._s.auto_commit()
        return new_val

    def restore_stat(self, character_id: str, stat: StatName, amount: int) -> int:
        if stat not in ("strength", "dexterity", "willpower"):
            raise ValueError(f"Invalid stat: {stat}")
        if amount < 1:
            raise ValueError("amount must be >= 1")
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Character '{character_id}' is dead")
        if char.status == CharacterStatus.DEPRIVED:
            raise ValueError(f"Character '{character_id}' is deprived — cannot restore stats")
        new_val = min(getattr(char, stat) + amount, getattr(char, f"max_{stat}"))
        self._set(character_id, **{stat: new_val})
        self._s.auto_commit()
        return new_val

    # ── Update / Move ──────────────────────────────────────────────────

    def update(self, character_id: str, field: CharacterField, value: str) -> None:
        allowed = {"status", "disposition", "location_id", "notes"}
        if field not in allowed:
            raise ValueError(f"Field '{field}' not allowed")
        if field == "status":
            CharacterStatus(value)
        if field == "disposition":
            Disposition(value)
        if field == "location_id" and value:
            char = self.get(character_id)
            if char.status == CharacterStatus.DEAD:
                raise ValueError("Cannot move dead character")
            self._ensure_location(value)
        self.get(character_id)  # ensure exists
        self._set(character_id, **{field: value})
        self._s.auto_commit()

    def move(self, character_id: str, location_id: str) -> None:
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Cannot move dead character '{character_id}'")
        self._ensure_location(location_id)
        if char.location_id:
            row = self._s.conn.execute(
                select(locations.c.connected_to).where(locations.c.id == char.location_id)
            ).fetchone()
            connected = json.loads(row[0]) if row else []
            if location_id not in connected:
                raise ValueError(
                    f"Location '{location_id}' is not reachable from '{char.location_id}'"
                )
        self._set(character_id, location_id=location_id)
        self._s.auto_commit()

    # ── Inventory ──────────────────────────────────────────────────────

    def add_item(self, character_id: str, item: str, bulky: bool = False) -> list[InventoryItem]:
        char = self.get(character_id)
        new_item = InventoryItem(name=item, slots=2 if bulky else 1, bulky=bulky)
        new_occupied = char.occupied_slots + new_item.slots
        if new_occupied > 10:
            raise ValueError(f"Inventory full: {char.occupied_slots}/10, item needs {new_item.slots}")
        char.inventory.append(new_item)
        self._save_inventory(character_id, char.inventory)
        if new_occupied == 10 and char.hp > 0:
            self._set(character_id, hp=0)
        self._s.auto_commit()
        return list(char.inventory)

    def remove_item(self, character_id: str, item: str) -> list[InventoryItem]:
        char = self.get(character_id)
        for i, inv_item in enumerate(char.inventory):
            if inv_item.name == item:
                char.inventory.pop(i)
                self._save_inventory(character_id, char.inventory)
                new_occupied = sum(it.slots for it in char.inventory) + char.fatigue
                if char.hp == 0 and new_occupied < 10:
                    self._set(character_id, hp=1)
                self._s.auto_commit()
                return list(char.inventory)
        raise ValueError(f"Item '{item}' not found in inventory of '{character_id}'")

    # ── Fatigue / Gold ─────────────────────────────────────────────────

    def add_fatigue(self, character_id: str) -> int:
        char = self.get(character_id)
        if char.status == CharacterStatus.DEAD:
            raise ValueError(f"Character '{character_id}' is dead")
        new_fatigue = char.fatigue + 1
        new_occupied = sum(i.slots for i in char.inventory) + new_fatigue
        updates: dict = {"fatigue": new_fatigue}
        if new_occupied >= 10 and char.hp > 0:
            updates["hp"] = 0
        self._set(character_id, **updates)
        self._s.auto_commit()
        return new_fatigue

    def remove_fatigue(self, character_id: str) -> int:
        char = self.get(character_id)
        if char.fatigue <= 0:
            raise ValueError(f"Character '{character_id}' has no fatigue")
        new_fatigue = char.fatigue - 1
        self._set(character_id, fatigue=new_fatigue)
        self._s.auto_commit()
        return new_fatigue

    def update_gold(self, character_id: str, amount: int) -> int:
        char = self.get(character_id)
        new_gold = char.gold + amount
        if new_gold < 0:
            raise ValueError(f"Not enough gold: has {char.gold}, spending {abs(amount)}")
        self._set(character_id, gold=new_gold)
        self._s.auto_commit()
        return new_gold

    # ── Helpers ─────────────────────────────────────────────────────────

    def _set(self, character_id: str, **values) -> None:
        self._s.conn.execute(
            update(characters).where(characters.c.id == character_id).values(**values)
        )

    def _save_inventory(self, character_id: str, inventory: list[InventoryItem]) -> None:
        data = json.dumps([{"name": i.name, "slots": i.slots, "bulky": i.bulky} for i in inventory])
        self._set(character_id, inventory=data)

    def _ensure_location(self, location_id: str) -> None:
        row = self._s.conn.execute(
            select(locations.c.id).where(locations.c.id == location_id)
        ).fetchone()
        if not row:
            raise KeyError(f"Location '{location_id}' not found")

    def _to_model(self, row) -> Character:
        return Character(
            id=row["id"], name=row["name"], class_=row["class_"],
            role=CharacterRole(row["role"]),
            strength=row["strength"], dexterity=row["dexterity"], willpower=row["willpower"],
            max_strength=row["max_strength"], max_dexterity=row["max_dexterity"],
            max_willpower=row["max_willpower"],
            hp=row["hp"], max_hp=row["max_hp"], armor=row["armor"], gold=row["gold"],
            inventory=[InventoryItem(**i) for i in json.loads(row["inventory"])],
            fatigue=row["fatigue"],
            status=CharacterStatus(row["status"]),
            location_id=row["location_id"], description=row["description"],
            disposition=Disposition(row["disposition"]) if row["disposition"] else Disposition.NEUTRAL,
            notes=row["notes"],
        )
