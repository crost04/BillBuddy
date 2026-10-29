"""Tests for login, logout and access control through the API."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


@pytest.fixture
def ben_client(app, client):
    """A second browser, logged in as Ben (Anna's browser stays logged in too)."""
    with TestClient(app) as ben:
        response = ben.post("/api/auth/register", json={"email": "ben@example.com", "name": "Ben", "password": PASSWORD})
        assert response.status_code == 201
        yield ben


@pytest.fixture
def anna_group(client):
    return client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()


def test_register_logs_in(client):
    me = client.get("/api/auth/me").json()
    assert (me["email"], me["name"]) == ("anna@example.com", "Anna")


def test_session_cookie_is_protected(anon_client):
    response = anon_client.post(
        "/api/auth/register", json={"email": "cem@example.com", "name": "Cem", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie  # local http:// needs this off


def test_cookie_is_secure_on_the_server(anon_client, monkeypatch):
    monkeypatch.setenv("BILLBUDDY_SECURE_COOKIES", "true")
    response = anon_client.post(
        "/api/auth/register", json={"email": "cem@example.com", "name": "Cem", "password": PASSWORD}
    )
    assert "Secure" in response.headers["set-cookie"]


def test_logout_and_login_again(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    response = client.post("/api/auth/login", json={"email": "ANNA@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_password_is_rejected(client):
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"email": "anna@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_too_many_failed_logins_are_blocked(client):
    client.post("/api/auth/logout")
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "anna@example.com", "password": "wrong"})
    # Even the right password is blocked for a while now
    response = client.post("/api/auth/login", json={"email": "anna@example.com", "password": PASSWORD})
    assert response.status_code == 429


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/auth/me"),
        ("get", "/api/groups"),
        ("post", "/api/groups"),
        ("get", "/api/groups/1/expenses"),
        ("get", "/api/groups/1/settlement"),
        ("get", "/api/expenses/1"),
        ("delete", "/api/payments/1"),
        ("get", "/api/invites/some-code"),
    ],
)
def test_data_needs_a_login(anon_client, method, path):
    assert getattr(anon_client, method)(path).status_code == 401


def test_public_endpoints(anon_client):
    assert anon_client.get("/api/health").json() == {"status": "ok"}
    assert anon_client.get("/api/categories").status_code == 200
    assert anon_client.get("/").status_code == 200


def test_creator_is_the_first_member(client, anna_group):
    me = client.get("/api/auth/me").json()
    anna, ben = anna_group["members"]
    assert (anna["name"], anna["user_id"]) == ("Anna", me["id"])
    assert (ben["name"], ben["user_id"]) == ("Ben", None)


def test_other_users_cannot_see_the_group(client, ben_client, anna_group):
    group_id = anna_group["id"]
    anna_member = anna_group["members"][0]
    expense = client.post(
        f"/api/groups/{group_id}/expenses",
        json={
            "payer_id": anna_member["id"],
            "amount": 10,
            "date": "2026-10-29",
            "description": "Rewe",
            "participants": [{"member_id": anna_member["id"]}],
        },
    ).json()

    assert ben_client.get("/api/groups").json() == []
    assert ben_client.get(f"/api/groups/{group_id}").status_code == 404
    assert ben_client.get(f"/api/groups/{group_id}/expenses").status_code == 404
    assert ben_client.get(f"/api/groups/{group_id}/settlement").status_code == 404
    assert ben_client.get(f"/api/expenses/{expense['id']}").status_code == 404
    assert ben_client.delete(f"/api/expenses/{expense['id']}").status_code == 404
    assert ben_client.put(f"/api/members/{anna_member['id']}", json={"name": "Hacked"}).status_code == 404


def test_join_with_invitation_link(client, ben_client, anna_group):
    code = anna_group["invite_code"]

    invite = ben_client.get(f"/api/invites/{code}").json()
    assert invite["group_name"] == "Home"
    assert [(m["name"], m["has_account"]) for m in invite["members"]] == [("Anna", True), ("Ben", False)]

    ben_member_id = invite["members"][1]["id"]
    response = ben_client.post(f"/api/invites/{code}/join", json={"member_id": ben_member_id})
    assert response.status_code == 200

    assert [g["name"] for g in ben_client.get("/api/groups").json()] == ["Home"]
    assert ben_client.get(f"/api/groups/{anna_group['id']}/settlement").status_code == 200


def test_wrong_invitation_code(ben_client):
    assert ben_client.get("/api/invites/wrong-code").status_code == 404
