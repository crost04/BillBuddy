"""Database setup shared by all modules.

By default the database lives in data/private/, which is git-ignored, so real
expenses never end up in the repository. Set BILLBUDDY_DATABASE_URL to use a
different database (e.g. one filled with sample data).
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "private" / "billbuddy.db"


class Base(DeclarativeBase):
    """Parent class of all database models."""


def get_database_url() -> str:
    url = os.environ.get("BILLBUDDY_DATABASE_URL")
    if url:
        return url
    # data/private/ is not in the repo, so create it on a fresh clone
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


def make_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    if not url.startswith("sqlite"):
        return create_engine(url)
    # FastAPI handles requests in several threads; SQLite must allow that
    kwargs = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # Share one connection, otherwise each connection gets its own empty in-memory database
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ignores foreign keys unless this is switched on for every connection
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables that do not exist yet."""
    # Import the models so they are registered on Base before creating tables
    from billbuddy.expenses import models  # noqa: F401

    Base.metadata.create_all(engine)
