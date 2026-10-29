"""Shared pytest fixtures."""

import pytest

from billbuddy.db import init_db, make_engine, make_session_factory


@pytest.fixture
def session():
    """A fresh in-memory database for each test, so tests never touch real data."""
    engine = make_engine("sqlite://")
    init_db(engine)
    with make_session_factory(engine)() as session:
        yield session
    engine.dispose()
