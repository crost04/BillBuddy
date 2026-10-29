"""Database setup shared by all modules.

Locally the database is a SQLite file in data/private/, which is git-ignored,
so real expenses never end up in the repository. On the server, DATABASE_URL
points to a PostgreSQL database instead (e.g. on Neon).
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "private" / "billbuddy.db"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


class Base(DeclarativeBase):
    """Parent class of all database models."""


def import_models() -> None:
    """Import every model module, so all tables are registered on Base."""
    from billbuddy.auth import models as auth_models  # noqa: F401
    from billbuddy.expenses import models as expense_models  # noqa: F401


def get_database_url() -> str:
    url = os.environ.get("BILLBUDDY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if url:
        # Hosts hand out "postgres://..." URLs; SQLAlchemy needs to know the driver
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url
    # data/private/ is not in the repo, so create it on a fresh clone
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


def make_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    if not url.startswith("sqlite"):
        # pool_pre_ping: a hosted database may close idle connections
        return create_engine(url, pool_pre_ping=True)
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


def init_db(engine: Engine, revision: str = "head") -> None:
    """Bring the database up to date by applying all migrations in migrations/.

    Migrations change the tables step by step and keep the existing data, so
    the app can evolve while real expenses are stored in it.
    """
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
