"""LocationRepository — CRUD, bidirectional connections."""

from __future__ import annotations

import json
import uuid
from typing import Literal

from sqlalchemy import select, update, insert

from contracts.world_state import LocationRepository as LocationRepositoryABC

from party_of_one.memory.db_session import DBSession
from party_of_one.memory.schema import locations
from party_of_one.models import Location

LocationField = Literal["description", "connected_to", "discovered"]


class LocationRepository(LocationRepositoryABC):
    def __init__(self, session: DBSession):
        self._s = session

    def get(self, location_id: str) -> Location:
        row = self._s.conn.execute(
            select(locations).where(locations.c.id == location_id)
        ).mappings().fetchone()
        if not row:
            raise KeyError(f"Location '{location_id}' not found")
        return self._to_model(row)

    def get_all(self) -> list[Location]:
        rows = self._s.conn.execute(select(locations)).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    def create(
        self, *, name: str, description: str, connected_to: list[str],
    ) -> Location:
        if not connected_to:
            raise ValueError("connected_to must not be empty")
        for lid in connected_to:
            self._ensure_exists(lid)
        loc_id = f"loc_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        self._s.conn.execute(insert(locations).values(
            id=loc_id, name=name, description=description,
            connected_to=json.dumps(connected_to), discovered=True,
        ))
        # Bidirectional links
        for other_id in connected_to:
            row = self._s.conn.execute(
                select(locations.c.connected_to).where(locations.c.id == other_id)
            ).fetchone()
            if row:
                others = json.loads(row[0])
                if loc_id not in others:
                    others.append(loc_id)
                    self._s.conn.execute(
                        update(locations)
                        .where(locations.c.id == other_id)
                        .values(connected_to=json.dumps(others))
                    )
        self._s.auto_commit()
        return self.get(loc_id)

    def create_initial(self, name: str, description: str) -> Location:
        """Create the very first location (no connections required)."""
        loc_id = f"loc_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        self._s.conn.execute(insert(locations).values(
            id=loc_id, name=name, description=description,
            connected_to="[]", discovered=True,
        ))
        self._s.auto_commit()
        return self.get(loc_id)

    def update(
        self, location_id: str, field: LocationField, value: str,
    ) -> None:
        allowed = {"description", "connected_to", "discovered"}
        if field not in allowed:
            raise ValueError(f"Field '{field}' not allowed")
        self._ensure_exists(location_id)
        if field == "connected_to":
            new_ids = json.loads(value)
            for lid in new_ids:
                self._ensure_exists(lid)
            # Get old connections for diff
            old_row = self._s.conn.execute(
                select(locations.c.connected_to).where(locations.c.id == location_id)
            ).fetchone()
            old_ids = json.loads(old_row[0]) if old_row else []
            # Update this location
            self._s.conn.execute(
                update(locations).where(locations.c.id == location_id)
                .values(connected_to=value)
            )
            # Add bidirectional links for new connections
            for lid in new_ids:
                if lid not in old_ids:
                    row = self._s.conn.execute(
                        select(locations.c.connected_to).where(locations.c.id == lid)
                    ).fetchone()
                    if row:
                        others = json.loads(row[0])
                        if location_id not in others:
                            others.append(location_id)
                            self._s.conn.execute(
                                update(locations).where(locations.c.id == lid)
                                .values(connected_to=json.dumps(others))
                            )
            # Remove reverse links for dropped connections
            for lid in old_ids:
                if lid not in new_ids:
                    row = self._s.conn.execute(
                        select(locations.c.connected_to).where(locations.c.id == lid)
                    ).fetchone()
                    if row:
                        others = json.loads(row[0])
                        if location_id in others:
                            others.remove(location_id)
                            self._s.conn.execute(
                                update(locations).where(locations.c.id == lid)
                                .values(connected_to=json.dumps(others))
                            )
            self._s.auto_commit()
            return
        if field == "discovered":
            value = True if value.lower() in ("true", "1") else False
        self._s.conn.execute(
            update(locations).where(locations.c.id == location_id).values(**{field: value})
        )
        self._s.auto_commit()

    def _ensure_exists(self, location_id: str) -> None:
        row = self._s.conn.execute(
            select(locations.c.id).where(locations.c.id == location_id)
        ).fetchone()
        if not row:
            raise KeyError(f"Location '{location_id}' not found")

    def _to_model(self, row) -> Location:
        return Location(
            id=row["id"], name=row["name"], description=row["description"],
            connected_to=json.loads(row["connected_to"]),
            discovered=bool(row["discovered"]),
        )
