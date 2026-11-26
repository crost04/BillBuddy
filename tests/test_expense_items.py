"""Receipt items stored with an expense (who bought what), through the API."""

import pytest


@pytest.fixture
def group(client):
    return client.post("/api/groups", json={"name": "WG", "members": ["Ben"]}).json()


def expense_body(group, items=None, **changes):
    anna, ben = group["members"]
    body = {
        "payer_id": anna["id"],
        "amount": 7.40,
        "date": "2026-11-20",
        "description": "dm",
        "split_method": "percent",
        "participants": [{"member_id": anna["id"], "percent": 70}, {"member_id": ben["id"], "percent": 30}],
    }
    if items is not None:
        body["items"] = items
    return body | changes


def scanned_items(group):
    anna, ben = group["members"]
    return [
        {"name": "Shampoo", "amount": 4.25, "member_id": anna["id"]},
        {"name": "Zahnpasta", "amount": 3.50, "member_id": None},
        {"name": "Rabatt", "amount": -0.35, "member_id": None},
    ]


def items_of(expense):
    return [(i["name"], i["amount"], i["member_id"]) for i in expense["items"]]


def test_items_are_saved_and_shown_in_order(client, group):
    anna = group["members"][0]
    response = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, scanned_items(group)))
    assert response.status_code == 201
    expense = client.get(f"/api/expenses/{response.json()['id']}").json()
    assert items_of(expense) == [("Shampoo", 4.25, anna["id"]), ("Zahnpasta", 3.5, None), ("Rabatt", -0.35, None)]
    listed = client.get(f"/api/groups/{group['id']}/expenses").json()
    assert len(listed[0]["items"]) == 3


def test_expense_without_items_has_an_empty_list(client, group):
    response = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group))
    assert response.json()["items"] == []


def test_edit_without_items_keeps_them_and_an_empty_list_removes_them(client, group):
    created = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, scanned_items(group))).json()
    url = f"/api/expenses/{created['id']}"

    # An edit that does not send items (e.g. an older app version) keeps them
    assert len(client.put(url, json=expense_body(group, description="dm Drogerie")).json()["items"]) == 3

    ben = group["members"][1]
    moved = [{"name": "Shampoo", "amount": 4.25, "member_id": ben["id"]}]
    assert items_of(client.put(url, json=expense_body(group, moved)).json()) == [("Shampoo", 4.25, ben["id"])]

    assert client.put(url, json=expense_body(group, [])).json()["items"] == []


def test_items_can_only_belong_to_members_of_the_group(client, group):
    stranger = client.post("/api/groups", json={"name": "Urlaub", "members": ["Cem"]}).json()["members"][1]
    items = [{"name": "Shampoo", "amount": 4.25, "member_id": stranger["id"]}]
    response = client.post(f"/api/groups/{group['id']}/expenses", json=expense_body(group, items))
    assert response.status_code == 422
