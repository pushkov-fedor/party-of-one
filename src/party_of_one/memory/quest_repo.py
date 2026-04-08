"""QuestRepository — CRUD, status transitions."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update, insert

from contracts.world_state import QuestRepository as QuestRepositoryABC

from party_of_one.memory.db_session import DBSession
from party_of_one.memory.schema import quests, characters
from party_of_one.models import Quest, QuestStatus


class QuestRepository(QuestRepositoryABC):
    def __init__(self, session: DBSession):
        self._s = session

    def get(self, quest_id: str) -> Quest:
        row = self._s.conn.execute(
            select(quests).where(quests.c.id == quest_id)
        ).mappings().fetchone()
        if not row:
            raise KeyError(f"Quest '{quest_id}' not found")
        return self._to_model(row)

    def get_all(self) -> list[Quest]:
        rows = self._s.conn.execute(select(quests)).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    def list(self, status: QuestStatus | None = None) -> list[Quest]:
        stmt = select(quests)
        if status:
            stmt = stmt.where(quests.c.status == status.value)
        rows = self._s.conn.execute(stmt).mappings().fetchall()
        return [self._to_model(r) for r in rows]

    def create(
        self, *, title: str, description: str, giver_character_id: str,
    ) -> Quest:
        # Validate giver exists
        row = self._s.conn.execute(
            select(characters.c.id).where(characters.c.id == giver_character_id)
        ).fetchone()
        if not row:
            raise KeyError(f"Character '{giver_character_id}' not found")
        quest_id = f"quest_{uuid.uuid4().hex[:8]}"
        self._s.conn.execute(insert(quests).values(
            id=quest_id, title=title, description=description,
            giver_character_id=giver_character_id,
        ))
        self._s.auto_commit()
        return self.get(quest_id)

    def update_status(self, quest_id: str, status: QuestStatus | str) -> None:
        if isinstance(status, str):
            status = QuestStatus(status)
        self.get(quest_id)  # ensure exists
        self._s.conn.execute(
            update(quests).where(quests.c.id == quest_id).values(status=status.value)
        )
        self._s.auto_commit()

    def _to_model(self, row) -> Quest:
        return Quest(
            id=row["id"], title=row["title"], description=row["description"],
            status=QuestStatus(row["status"]),
            giver_character_id=row["giver_character_id"],
        )
