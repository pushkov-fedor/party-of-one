"""TurnRepository — raw turns and compressed history."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, insert

from contracts.world_state import TurnRepository as TurnRepositoryABC

from party_of_one.memory.db_session import DBSession
from party_of_one.memory.schema import turns, compressed_history
from party_of_one.models import CompressedHistory, Turn, TurnRole


class TurnRepository(TurnRepositoryABC):
    def __init__(self, session: DBSession):
        self._s = session

    def save_turn(self, turn: Turn) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._s.conn.execute(insert(turns).values(
            turn_number=turn.turn_number,
            role=turn.role.value if isinstance(turn.role, TurnRole) else turn.role,
            content=turn.content,
            commands=json.dumps(turn.commands) if turn.commands else None,
            created_at=now,
        ))
        self._s.auto_commit()

    def get_recent(self, n: int) -> list[Turn]:
        rows = self._s.conn.execute(
            select(turns).order_by(turns.c.id.desc()).limit(n)
        ).mappings().fetchall()
        return [self._to_turn(r) for r in reversed(rows)]

    def save_compressed_history(self, history: CompressedHistory) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._s.conn.execute(insert(compressed_history).values(
            summary=history.summary,
            covers_turns_from=history.covers_turns_from,
            covers_turns_to=history.covers_turns_to,
            created_at=now,
        ))
        self._s.auto_commit()

    def get_compressed_history(self) -> list[CompressedHistory]:
        rows = self._s.conn.execute(
            select(compressed_history).order_by(compressed_history.c.id)
        ).mappings().fetchall()
        return [
            CompressedHistory(
                id=r["id"], summary=r["summary"],
                covers_turns_from=r["covers_turns_from"],
                covers_turns_to=r["covers_turns_to"],
                created_at=datetime.fromisoformat(r["created_at"])
                if r["created_at"] else datetime.now(timezone.utc),
            )
            for r in rows
        ]

    def _to_turn(self, row) -> Turn:
        return Turn(
            id=row["id"], turn_number=row["turn_number"],
            role=TurnRole(row["role"]),
            content=row["content"],
            commands=json.loads(row["commands"]) if row["commands"] else None,
            created_at=datetime.fromisoformat(row["created_at"])
            if row["created_at"] else datetime.now(timezone.utc),
        )
