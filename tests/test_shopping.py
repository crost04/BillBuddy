"""Tests for the shared shopping list (billbuddy.shopping) and its API."""

import pytest

from billbuddy.expenses.models import Group, Member
from billbuddy.expenses.service import ValidationError
from billbuddy.shopping import service


@pytest.fixture
def group(session):
    group = Group(name="WG", members=[Member(name="Anna"), Member(name="Ben")])
    session.add(group)
    session.commit()
    return group


def names(session, group):
    return [(i.name, i.checked) for i in service.list_items(session, group.id)]


def test_open_entries_first_in_the_order_they_were_added(session, group):
    milk = service.add_item(session, group.id, "Milch", None)
    service.add_item(session, group.id, "Brot", None)
    service.update_item(session, milk, checked=True)
    service.add_item(session, group.id, "Käse", None)
    assert names(session, group) == [("Brot", False), ("Käse", False), ("Milch", True)]


def test_the_same_entry_is_not_added_twice(session, group):
    first = service.add_item(session, group.id, "Milch", None)
    again = service.add_item(session, group.id, "  milch ", None)
    assert again.id == first.id
    assert names(session, group) == [("Milch", False)]


def test_a_ticked_off_entry_can_be_added_again(session, group):
    milk = service.add_item(session, group.id, "Milch", None)
    service.update_item(session, milk, checked=True)
    service.add_item(session, group.id, "Milch", None)
    assert names(session, group) == [("Milch", False), ("Milch", True)]


def test_empty_names_are_refused(session, group):
    with pytest.raises(ValidationError):
        service.add_item(session, group.id, "   ", None)


def test_remove_ignores_entries_of_other_groups(session, group):
    other = Group(name="Urlaub", members=[Member(name="Cem")])
    session.add(other)
    session.commit()
    mine = service.add_item(session, group.id, "Milch", None)
    theirs = service.add_item(session, other.id, "Sonnencreme", None)
    assert service.remove_items(session, group.id, [mine.id, theirs.id]) == 1
    assert names(session, group) == []
    assert [i.name for i in service.list_items(session, other.id)] == ["Sonnencreme"]


# --- API ---


@pytest.fixture
def api_group(client):
    return client.post("/api/groups", json={"name": "WG", "members": ["Ben"]}).json()


def test_api_add_tick_off_and_remove(client, api_group):
    url = f"/api/groups/{api_group['id']}/shopping-items"
    anna = api_group["members"][0]

    response = client.post(url, json={"name": "Milch"})
    assert response.status_code == 201
    milk = response.json()
    assert (milk["name"], milk["checked"], milk["added_by_id"]) == ("Milch", False, anna["id"])
    bread = client.post(url, json={"name": "Brot"}).json()

    assert client.put(f"/api/shopping-items/{milk['id']}", json={"checked": True}).json()["checked"]
    assert [(i["name"], i["checked"]) for i in client.get(url).json()] == [("Brot", False), ("Milch", True)]

    response = client.post(f"{url}/remove", json={"ids": [milk["id"]]})
    assert response.json() == {"removed": 1}
    assert client.delete(f"/api/shopping-items/{bread['id']}").status_code == 204
    assert client.get(url).json() == []


def test_api_list_of_another_group_is_not_visible(client, api_group):
    item = client.post(f"/api/groups/{api_group['id']}/shopping-items", json={"name": "Milch"}).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "eve@example.com", "name": "Eve", "password": "another-password"})
    assert client.get(f"/api/groups/{api_group['id']}/shopping-items").status_code == 404
    assert client.put(f"/api/shopping-items/{item['id']}", json={"checked": True}).status_code == 404
    assert client.delete(f"/api/shopping-items/{item['id']}").status_code == 404
