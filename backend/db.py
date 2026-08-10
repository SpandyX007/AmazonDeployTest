"""Engine, session factory, and the declarative base.

One `DATABASE_URL` decides whether this is a local SQLite file or a managed
Postgres — no other module knows the difference.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # FastAPI runs sync endpoints on a threadpool, so a pooled connection can
    # surface on a different thread than the one that opened it.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
    future=True,
)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection, _record):  # pragma: no cover - driver hook
        cursor = connection.cursor()
        # ON DELETE CASCADE is opt-in on SQLite; without this, deleting an
        # account would leave its conversations behind.
        cursor.execute("PRAGMA foreign_keys=ON")
        # Readers stop blocking the writer — matters as soon as a streaming
        # turn and a sidebar refresh overlap.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; re-attach UTC so comparisons work."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def get_db() -> Iterator[Session]:
    """Request-scoped session.

    Careful: FastAPI tears this down when the endpoint *returns*, which for a
    StreamingResponse is before the body has finished producing. Anything a
    stream needs to write afterwards opens its own session — see `backend.chat`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables. Enough for a schema that only grows;
    swap in Alembic once a column needs to change shape in production."""
    from backend import models  # noqa: F401  (import registers the tables)

    Base.metadata.create_all(engine)
