"""Tests for the REST API in billbuddy.api."""

import pytest


@pytest.fixture
def group(client):
    response = client.post("/api/groups", json={"name": "Home", "members": ["Anna", "Ben"]})
    assert response.status_code == 201
    return response.json()


def expense_body(group, **changes):
    anna, ben = group["members"]
    body = {
        "payer_id": anna["id"],
        "amount": 34.5,
        "date": "2026-10-29",
        "description": "Rewe",
        "participants": [{"member_id": anna["id"]}, {"member_id": ben["id"]}],
    }
    return {**body, **changes}


def test_categories(client):
    assert "Groceries" in client.get("/api/categories").json()


def test_create_and_list_groups(client, group):
    assert [m["name"] for m in group["members"]] == ["Anna", "Ben"]
    assert client.get("/api/groups").json() == [group]
    assert client.get(f"/api/groups/{group['id']}").json() == group


def test_add_and_update_member(client, group):
    response = client.post(f"/api/groups/{group['id']}/members", json={"name": "Cem"})
    assert response.status_code == 201
    cem = response.json()

    response = client.put(f"/api/members/{cem['id']}", json={"name": "Cem", "monthly_income": 2100.5})
    assert response.json()["monthly_income"] == 2100.5


def test_expense_lifecycle(client, group):
    # Create
    response = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group))
    assert response.status_code == 201
    expense = response.json()
    assert expense["amount"] == 34.5
    assert expense["split_method"] == "equal"
    assert len(expense["shares"]) == 2

    # Read
    assert client.get(f"/api/expenses/{expense['id']}").json() == expense

    # Update
    body = expense_body(group, amount=12.99, category="Groceries")
    updated = client.put(f"/api/expenses/{expense['id']}", json=body).json()
    assert (updated["amount"], updated["category"]) == (12.99, "Groceries")

    # Delete
    assert client.delete(f"/api/expenses/{expense['id']}").status_code == 204
    assert client.get(f"/api/expenses/{expense['id']}").status_code == 404


def test_list_expenses_by_month(client, group):
    for date in ("2026-09-30", "2026-10-01", "2026-10-31"):
        client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, date=date))

    october = client.get(f"/api/groups/{group['id']}/expenses", params={"month": "2026-10"}).json()
    assert [e["date"] for e in october] == ["2026-10-31", "2026-10-01"]
    assert len(client.get(f"/api/groups/{group['id']}/expenses").json()) == 3


def test_percent_split(client, group):
    anna, ben = group["members"]
    body = expense_body(
        group,
        split_method="percent",
        participants=[
            {"member_id": anna["id"], "percent": 60},
            {"member_id": ben["id"], "percent": 40},
        ],
    )
    response = client.post(f"/api/groups/{group['id']}/expenses", json=body)
    assert response.status_code == 201
    assert sorted(s["percent"] for s in response.json()["shares"]) == [40, 60]


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": -5},
        {"amount": 1.234},  # more than two decimals
        {"description": ""},
        {"participants": []},
        {"category": "Unicorns"},
        {"split_method": "percent"},  # percentages missing
    ],
)
def test_invalid_expenses_return_422(client, group, changes):
    response = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, **changes))
    assert response.status_code == 422


def test_unknown_ids_return_404(client, group):
    assert client.get("/api/groups/999").status_code == 404
    assert client.get("/api/expenses/999").status_code == 404
    assert client.post("/api/groups/999/expenses", json=expense_body(group)).status_code == 404


# --- Settlement ---


def test_settlement_and_payments(client, group):
    anna, ben = group["members"]
    client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, amount=60))

    settlement = client.get(f"/api/groups/{group['id']}/settlement").json()
    assert settlement["balances"] == [
        {"member_id": anna["id"], "balance": 30.0},
        {"member_id": ben["id"], "balance": -30.0},
    ]
    assert settlement["transfers"] == [
        {"from_member_id": ben["id"], "to_member_id": anna["id"], "amount": 30.0}
    ]

    # Ben pays Anna back
    body = {"from_member_id": ben["id"], "to_member_id": anna["id"], "amount": 30, "date": "2026-10-30"}
    response = client.post(f"/api/groups/{group['id']}/payments", json=body)
    assert response.status_code == 201
    payment = response.json()

    settlement = client.get(f"/api/groups/{group['id']}/settlement").json()
    assert [b["balance"] for b in settlement["balances"]] == [0, 0]
    assert settlement["transfers"] == []

    assert client.get(f"/api/groups/{group['id']}/payments").json() == [payment]
    assert client.delete(f"/api/payments/{payment['id']}").status_code == 204
    assert client.get(f"/api/groups/{group['id']}/payments").json() == []


def test_invalid_payment_returns_422(client, group):
    anna, _ = group["members"]
    body = {"from_member_id": anna["id"], "to_member_id": anna["id"], "amount": 10, "date": "2026-10-30"}
    assert client.post(f"/api/groups/{group['id']}/payments", json=body).status_code == 422
