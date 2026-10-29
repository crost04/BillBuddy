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


PASSWORD = "secret-password"


@pytest.fixture
def app():
    """The whole app (API + web app) with a fresh in-memory database."""
    return create_app(make_engine("sqlite://"))


@pytest.fixture
def anon_client(app):
    """A browser that is not logged in."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(anon_client):
    """A browser logged in as Anna (the login cookie is kept automatically)."""
    response = anon_client.post(
        "/api/auth/register", json={"email": "anna@example.com", "name": "Anna", "password": PASSWORD}
    )
    assert response.status_code == 201
    return anon_client
