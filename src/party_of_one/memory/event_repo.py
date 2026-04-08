"""EventRepository — append-only timeline."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, insert

from contracts.world_state import EventRepository as EventRepositoryABC

from party_of_one.memory.db_session import DBSession
from party_of_one.memory.schema import events
from party_of_one.models import Event, EventType


class EventRepository(EventRepositoryABC):
    def __init__(self, session: DBSession):
        self._s = session

    def add(self, description: str, event_type: EventType | str) -> Event:
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        now = datetime.now(timezone.utc).isoformat()
        result = self._s.conn.execute(insert(events).values(
            turn_number=0, description=description,
            event_type=event_type.value, created_at=now,
        ))
        self._s.auto_commit()
        return Event(
            id=result.lastrowid, turn_number=0,
            description=description, event_type=event_type,
            created_at=datetime.fromisoformat(now),
        )

    def get_recent(self, last_n: int | None = None) -> list[Event]:
        if last_n is not None:
            rows = self._s.conn.execute(
                select(events).order_by(events.c.id.desc()).limit(last_n)
            ).mappings().fetchall()
            rows = list(reversed(rows))
        else:
            rows = self._s.conn.execute(
                select(events).order_by(events.c.turn_number)
            ).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    def _to_model(self, row) -> Event:
        return Event(
            id=row["id"], turn_number=row["turn_number"],
            description=row["description"],
            event_type=EventType(row["event_type"]),
            created_at=datetime.fromisoformat(row["created_at"])
            if row["created_at"] else datetime.now(timezone.utc),
        )
