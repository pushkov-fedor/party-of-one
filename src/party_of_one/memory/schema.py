"""SQLAlchemy Core schema for World State."""

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)

metadata = MetaData()

characters = Table(
    "characters",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("class_", String, nullable=False, default=""),
    Column("role", String, nullable=False, default="npc"),
    Column("strength", Integer, nullable=False),
    Column("dexterity", Integer, nullable=False),
    Column("willpower", Integer, nullable=False),
    Column("max_strength", Integer, nullable=False),
    Column("max_dexterity", Integer, nullable=False),
    Column("max_willpower", Integer, nullable=False),
    Column("hp", Integer, nullable=False),
    Column("max_hp", Integer, nullable=False),
    Column("armor", Integer, nullable=False, default=0),
    Column("gold", Integer, nullable=False, default=0),
    Column("inventory", Text, nullable=False, default="[]"),
    Column("fatigue", Integer, nullable=False, default=0),
    Column("status", String, nullable=False, default="alive"),
    Column("location_id", String, nullable=False, default=""),
    Column("description", String, nullable=False, default=""),
    Column("disposition", String, nullable=False, default="neutral"),
    Column("notes", String, nullable=False, default=""),
)

locations = Table(
    "locations",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("connected_to", Text, nullable=False, default="[]"),
    Column("discovered", Boolean, nullable=False, default=False),
)

quests = Table(
    "quests",
    metadata,
    Column("id", String, primary_key=True),
    Column("title", String, nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("status", String, nullable=False, default="active"),
    Column("giver_character_id", String, nullable=False, default=""),
)

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("turn_number", Integer, nullable=False, default=0),
    Column("description", Text, nullable=False, default=""),
    Column("event_type", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
)

turns = Table(
    "turns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("turn_number", Integer, nullable=False, default=0),
    Column("role", String, nullable=False, default=""),
    Column("content", Text, nullable=False, default=""),
    Column("commands", Text, nullable=True),
    Column("created_at", String, nullable=False, default=""),
)

compressed_history = Table(
    "compressed_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("summary", Text, nullable=False, default=""),
    Column("covers_turns_from", Integer, nullable=False, default=0),
    Column("covers_turns_to", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False, default=""),
)


def init_db(db_path: str):
    """Create engine, ensure all tables exist, return engine."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    metadata.create_all(engine)
    return engine
