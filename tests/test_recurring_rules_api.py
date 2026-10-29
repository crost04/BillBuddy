"""API tests for standing orders and dismissed fixed-cost suggestions."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from billbuddy.api import expense_routes, recurring_routes
from billbuddy.ml.recurring import service as recurring_service
from tests.conftest import PASSWORD

TODAY = dt.date(2026, 10, 29)


@pytest.fixture
def group(client, monkeypatch):
    for module in (expense_routes, recurring_routes, recurring_service):
        monkeypatch.setattr(module, "today", lambda: TODAY)
    return client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()


def add(client, group, description, amount, date, category=None):
    anna, ben = group["members"]
    response = client.post(
        f"/api/groups/{group['id']}/expenses",
        json={
            "payer_id": anna["id"],
            "amount": amount,
            "date": date,
            "description": description,
            "category": category,
            "participants": [{"member_id": anna["id"]}, {"member_id": ben["id"]}],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_standing_order_books_monthly_entries(client, group):
    rent = add(client, group, "Miete August", 950, "2026-08-01", "Rent")

    response = client.post(f"/api/groups/{group['id']}/recurring-rules", json={"expense_id": rent["id"]})
    assert response.status_code == 201
    rule = response.json()
    assert (rule["description"], rule["amount"]) == ("Miete", 950.0)
    assert (rule["day_of_month"], rule["next_date"]) == (1, "2026-09-01")

    # Opening the expense list books September and October
    expenses = client.get(f"/api/groups/{group['id']}/expenses").json()
    assert [(e["date"], e["description"]) for e in expenses] == [
        ("2026-10-01", "Miete"),
        ("2026-09-01", "Miete"),
        ("2026-08-01", "Miete August"),
    ]
    assert all(e["is_fixed"] and e["recurring_rule_id"] == rule["id"] for e in expenses)

    [listed] = client.get(f"/api/groups/{group['id']}/recurring-rules").json()
    assert listed["next_date"] == "2026-11-01"


def test_change_amount_and_stop(client, group):
    rent = add(client, group, "Miete", 950, "2026-10-01", "Rent")
    rule = client.post(f"/api/groups/{group['id']}/recurring-rules", json={"expense_id": rent["id"]}).json()

    updated = client.put(f"/api/recurring-rules/{rule['id']}", json={"amount": 990})
    assert updated.json()["amount"] == 990.0

    assert client.delete(f"/api/recurring-rules/{rule['id']}").status_code == 204
    assert client.get(f"/api/groups/{group['id']}/recurring-rules").json() == []
    # The entry it was created from stays
    assert len(client.get(f"/api/groups/{group['id']}/expenses").json()) == 1


def test_recognized_series_shows_whether_it_has_a_standing_order(client, group):
    for month in (7, 8, 9, 10):
        last = add(client, group, "Netflix", 13.99, f"2026-{month:02d}-10", "Subscriptions")

    [series] = client.get(f"/api/groups/{group['id']}/recurring").json()
    assert not series["has_rule"]
    assert series["last_expense_id"] == last["id"]

    client.post(f"/api/groups/{group['id']}/recurring-rules", json={"expense_id": series["last_expense_id"]})
    [series] = client.get(f"/api/groups/{group['id']}/recurring").json()
    assert series["has_rule"] and series["already_fixed"]


def test_dismissed_series_is_not_suggested_again(client, group):
    for month in (7, 8, 9, 10):
        add(client, group, "Wochenmarkt", 20, f"2026-{month:02d}-03", "Groceries")
    assert len(client.get(f"/api/groups/{group['id']}/recurring").json()) == 1

    assert client.post(f"/api/groups/{group['id']}/recurring/dismiss", json={"key": "wochenmarkt"}).status_code == 204
    client.post(f"/api/groups/{group['id']}/recurring/dismiss", json={"key": "wochenmarkt"})  # twice is fine
    assert client.get(f"/api/groups/{group['id']}/recurring").json() == []


def test_other_users_cannot_touch_standing_orders(app, client, group):
    rent = add(client, group, "Miete", 950, "2026-10-01", "Rent")
    rule = client.post(f"/api/groups/{group['id']}/recurring-rules", json={"expense_id": rent["id"]}).json()

    with TestClient(app) as ben:
        ben.post("/api/auth/register", json={"email": "ben@example.com", "name": "Ben", "password": PASSWORD})
        assert ben.put(f"/api/recurring-rules/{rule['id']}", json={"amount": 1}).status_code == 404
        assert ben.delete(f"/api/recurring-rules/{rule['id']}").status_code == 404
        assert ben.get(f"/api/groups/{group['id']}/recurring-rules").status_code == 404
        response = ben.post(f"/api/groups/{group['id']}/recurring-rules", json={"expense_id": rent["id"]})
        assert response.status_code == 404
