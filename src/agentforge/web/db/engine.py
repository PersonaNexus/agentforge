"""Database engine creation and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_DB_PATH = "agentforge.db"


def get_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    Args:
        url: Database URL. If None, reads AGENTFORGE_DATABASE_URL env var,
             falling back to a local SQLite file.

    Returns:
        Configured SQLAlchemy Engine.
    """
    if url is None:
        url = os.environ.get("AGENTFORGE_DATABASE_URL")
    if url is None:
        db_path = Path(_DEFAULT_DB_PATH).resolve()
        url = f"sqlite:///{db_path}"

    connect_args = {}
    extra_kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # In-memory SQLite needs StaticPool to share the DB across connections
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool

            extra_kwargs["poolclass"] = StaticPool

    engine = create_engine(url, connect_args=connect_args, echo=False, **extra_kwargs)

    # Enable WAL mode and foreign keys for SQLite (file-based only)
    if url.startswith("sqlite"):
        is_file_db = ":memory:" not in url

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            if is_file_db:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables if they don't exist."""
    from agentforge.web.db.models import Base

    Base.metadata.create_all(engine)
