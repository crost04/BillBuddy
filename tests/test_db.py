"""Tests for the database setup in billbuddy.db."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from billbuddy.db import Base, get_database_url, import_models, init_db, make_engine


def test_migrations_match_the_models():
    """Fails when a model was changed without creating a migration for it."""
    import_models()
    engine = make_engine("sqlite://")
    init_db(engine)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []


def test_init_db_can_run_twice():
    engine = make_engine("sqlite://")
    init_db(engine)
    init_db(engine)


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
        ("sqlite:///demo.db", "sqlite:///demo.db"),
    ],
)
def test_database_url_from_environment(monkeypatch, given, expected):
    monkeypatch.delenv("BILLBUDDY_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", given)
    assert get_database_url() == expected


def test_default_database_is_private(monkeypatch):
    monkeypatch.delenv("BILLBUDDY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url().endswith("data/private/billbuddy.db")
