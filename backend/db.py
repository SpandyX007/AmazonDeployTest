"""Engine, session factory, and the declarative base.

The database is AWS RDS PostgreSQL. `backend.config` resolves the URL and the
TLS options; this module owns the engine; nothing else in the package touches
the driver — every other file asks for a `Session` and speaks SQLAlchemy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import DATABASE_URL, DB_CONNECT_ARGS, DB_MAX_OVERFLOW, DB_POOL_SIZE

log = logging.getLogger("uvicorn.error")

DB_URL = make_url(DATABASE_URL)
if DB_URL.get_backend_name() != "postgresql":
    raise RuntimeError(
        "DATABASE_URL must point at PostgreSQL (postgresql+psycopg://...), "
        f"not '{DB_URL.drivername}'"
    )

engine = create_engine(
    DB_URL,
    connect_args=DB_CONNECT_ARGS,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    # The database is across a network now. A pooled connection can die
    # underneath us — an RDS failover, a maintenance restart, an idle timeout
    # on a NAT — and pre-ping swaps a dead one for a fresh one instead of
    # handing the request a stack trace.
    pool_pre_ping=True,
    # ...and recycling well inside any idle limit means a quiet hour does not
    # leave the pool full of connections the other side has forgotten.
    pool_recycle=1800,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """`timestamptz` columns come back timezone-aware, so this is normally a
    no-op. It stays as a guard: a naive value from anywhere else must not blow
    up a comparison against `utcnow()`."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def describe() -> str:
    """Where we are connected, password blanked — for the boot log."""
    return f"{DB_URL.render_as_string(hide_password=True)} (sslmode={DB_CONNECT_ARGS['sslmode']})"


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
    """Make sure the database exists, then create any missing tables.

    `create_all` is enough for a schema that only grows; swap in Alembic once
    a column needs to change shape on data that must survive.
    """
    from backend import models  # noqa: F401  (import registers the tables)

    _ensure_database()
    Base.metadata.create_all(engine)


def _ensure_database() -> None:
    """Create the target database on the instance if it is not there yet.

    A fresh RDS instance has only the default `postgres` database. Rather than
    make the first deploy a manual `CREATE DATABASE`, borrow that one for a
    moment and create ours; every later boot connects straight through.
    """
    try:
        with engine.connect():
            return
    except OperationalError as exc:
        # Wrong host, bad password, blocked security group: surface as-is.
        if "does not exist" not in str(exc):
            raise

    name = DB_URL.database
    log.info("Database %r not found on %s — creating it", name, DB_URL.host)
    maintenance = create_engine(
        DB_URL.set(database="postgres"),
        connect_args=DB_CONNECT_ARGS,
        poolclass=NullPool,
        # CREATE DATABASE refuses to run inside a transaction block.
        isolation_level="AUTOCOMMIT",
    )
    try:
        with maintenance.connect() as conn:
            quoted = conn.dialect.identifier_preparer.quote(name)
            try:
                conn.execute(text(f"CREATE DATABASE {quoted}"))
            except ProgrammingError as exc:
                # Two workers booting at once: the other one won the race.
                if "already exists" not in str(exc):
                    raise
    finally:
        maintenance.dispose()
