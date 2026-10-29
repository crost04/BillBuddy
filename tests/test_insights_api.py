"""API tests for recognized fixed costs and anomalies."""

import datetime as dt

import pytest

from billbuddy.api import anomaly_routes
from billbuddy.ml.recurring import service as recurring_service

TODAY = dt.date(2026, 10, 29)


@pytest.fixture
def group(client, monkeypatch):
    monkeypatch.setattr(recurring_service, "today", lambda: TODAY)
    monkeypatch.setattr(anomaly_routes, "today", lambda: TODAY)
    return client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()


def add(client, group, description, amount, date, category=None):
    anna = group["members"][0]
    response = client.post(
        f"/api/groups/{group['id']}/expenses",
        json={
            "payer_id": anna["id"],
            "amount": amount,
            "date": date,
            "description": description,
            "category": category,
            "participants": [{"member_id": anna["id"]}],
        },
    )
    assert response.status_code == 201
    return response.json()


def add_groceries(client, group):
    amounts = [15, 22, 28, 33, 38, 45, 52, 61, 25, 35]
    for i, amount in enumerate(amounts):
        add(client, group, "Rewe", amount, f"2026-09-{i + 1:02d}", "Groceries")


# --- Recurring costs ---


def test_recognized_fixed_costs_can_be_marked(client, group):
    for month in range(6, 11):
        add(client, group, "Netflix", 13.99, f"2026-{month:02d}-10", "Subscriptions")

    [series] = client.get(f"/api/groups/{group['id']}/recurring").json()
    assert series["key"] == "netflix"
    assert (series["typical_amount"], series["day_of_month"], series["next_date"]) == (13.99, 10, "2026-11-10")
    assert series["active"] and not series["already_fixed"]

    response = client.post(f"/api/groups/{group['id']}/recurring/mark-fixed", json={"key": "netflix"})
    assert response.json() == {"changed": 5}

    [series] = client.get(f"/api/groups/{group['id']}/recurring").json()
    assert series["already_fixed"]
    expenses = client.get(f"/api/groups/{group['id']}/expenses").json()
    assert all(e["is_fixed"] for e in expenses)


# --- Check before saving ---


def test_check_finds_a_duplicate(client, group):
    existing = add(client, group, "Rewe", 34.5, "2026-10-28", "Groceries")
    body = {"amount": 34.5, "date": "2026-10-29", "description": "REWE Kartenzahlung", "category": "Groceries"}

    result = client.post(f"/api/groups/{group['id']}/check-expense", json=body).json()
    assert [d["id"] for d in result["duplicates"]] == [existing["id"]]

    # When editing that very expense, it is not its own duplicate
    result = client.post(f"/api/groups/{group['id']}/check-expense", json={**body, "expense_id": existing["id"]}).json()
    assert result["duplicates"] == []


def test_check_finds_an_unusual_amount(client, group):
    add_groceries(client, group)
    body = {"amount": 345, "date": "2026-10-29", "description": "Edeka", "category": "Groceries"}

    outlier = client.post(f"/api/groups/{group['id']}/check-expense", json=body).json()["outlier"]
    assert outlier["is_outlier"]
    assert outlier["typical"] == 34.0
    assert outlier["ratio"] > 8

    normal = client.post(f"/api/groups/{group['id']}/check-expense", json={**body, "amount": 40}).json()["outlier"]
    assert not normal["is_outlier"]


# --- Overview list ---


def test_anomalies_of_the_month(client, group):
    add_groceries(client, group)
    first = add(client, group, "Rewe", 34.5, "2026-10-20", "Groceries")
    second = add(client, group, "rewe", 34.5, "2026-10-20", "Groceries")
    typo = add(client, group, "Edeka", 345, "2026-10-25", "Groceries")

    anomalies = client.get(f"/api/groups/{group['id']}/anomalies", params={"month": "2026-10"}).json()
    assert [(a["kind"], a["expense"]["id"]) for a in anomalies] == [
        ("outlier", typo["id"]),
        ("duplicate", second["id"]),
    ]
    assert anomalies[1]["other"]["id"] == first["id"]
    assert anomalies[0]["ratio"] > 8

    assert client.get(f"/api/groups/{group['id']}/anomalies", params={"month": "2026-08"}).json() == []


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/groups/999/recurring"),
        ("get", "/api/groups/999/anomalies"),
    ],
)
def test_other_groups_are_not_accessible(client, method, path):
    assert getattr(client, method)(path).status_code == 404
