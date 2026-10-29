"""Tests for the database setup in billbuddy.db."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

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


def test_migrations_keep_existing_data():
    """Simulates an update of the live app: old database with data -> newest version."""
    engine = make_engine("sqlite://")
    init_db(engine, revision="c28fbd0b2bd7")  # the first version of the database
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO groups (name, invite_code, created_at) VALUES ('Home', 'abc', '2026-10-29')")
        )
        connection.execute(text("INSERT INTO members (group_id, name) VALUES (1, 'Anna')"))
        connection.execute(text(
            "INSERT INTO expenses (group_id, payer_id, amount_cents, date, description, is_fixed, split_method, created_at) "
            "VALUES (1, 1, 3450, '2026-10-29', 'Rewe', 0, 'EQUAL', '2026-10-29')"
        ))

    init_db(engine)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT description, amount_cents FROM expenses")).all() == [("Rewe", 3450)]
    assert "suggested_category" in {c["name"] for c in inspect(engine).get_columns("expenses")}
