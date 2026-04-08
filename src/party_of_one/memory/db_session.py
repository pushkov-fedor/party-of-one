"""Shared DB session for all repositories — wraps SQLAlchemy connection."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.engine import Connection


class DBSession:
    """Lightweight container shared by all repositories.

    Uses SQLAlchemy's autobegin — no explicit begin() needed.
    The in_transaction flag prevents auto_commit() during batch operations.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.conn: Connection = engine.connect()
        self.in_transaction = False

    def close(self):
        self.conn.close()

    def auto_commit(self):
        if not self.in_transaction:
            self.conn.commit()

    @contextmanager
    def transaction(self):
        """Batch operations: suppress auto_commit, commit/rollback at the end."""
        self.in_transaction = True
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self.in_transaction = False
