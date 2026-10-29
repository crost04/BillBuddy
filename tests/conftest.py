"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from billbuddy.api.main import create_app
from billbuddy.db import init_db, make_engine, make_session_factory


@pytest.fixture
def session():
    """A fresh in-memory database for each test, so tests never touch real data."""
    engine = make_engine("sqlite://")
    init_db(engine)
    with make_session_factory(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client():
    """The whole app (API + web app) with a fresh in-memory database."""
    with TestClient(create_app(make_engine("sqlite://"))) as client:
        yield client
