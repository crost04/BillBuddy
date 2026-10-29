"""Tests for the CSV export (billbuddy.settlement.export)."""

import csv
import io

import pytest

from billbuddy.api import settlement_routes


@pytest.fixture
def group(client, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(settlement_routes, "today", lambda: dt.date(2026, 10, 29))
    group = client.post("/api/groups", json={"name": "WG Süd", "members": ["Ben"]}).json()
    anna, ben = group["members"]
    client.post(
        f"/api/groups/{group['id']}/expenses",
        json={
            "payer_id": anna["id"],
            "amount": 34.5,
            "date": "2026-10-20",
            "description": "Rewe; Einkauf",  # a ";" inside a value must not break the columns
            "category": "Groceries",
            "participants": [{"member_id": anna["id"]}, {"member_id": ben["id"]}],
        },
    )
    client.post(
        f"/api/groups/{group['id']}/payments",
        json={"from_member_id": ben["id"], "to_member_id": anna["id"], "amount": 17.25, "date": "2026-10-25"},
    )
    return group


def read(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # Excel needs this to show umlauts
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def test_export_contains_expenses_and_payments(client, group):
    response = client.get(f"/api/groups/{group['id']}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="billbuddy-wg-s-d-2026-10-29.csv"' in response.headers["content-disposition"]

    header, expense, payment = read(response)
    assert header[:4] == ["Datum", "Art", "Beschreibung", "Betrag"]
    assert expense == [
        "2026-10-20",
        "Ausgabe",
        "Rewe; Einkauf",
        "34,50",
        "Lebensmittel",
        "Anna",
        "nein",
        "nein",
        "gleich",
        "Anna 17,25 €; Ben 17,25 €",
    ]
    assert payment[:4] == ["2026-10-25", "Ausgleichszahlung", "Ben → Anna", "17,25"]
    assert payment[-1] == "an Anna"


def test_export_needs_access(client, anon_client, group):
    assert client.get("/api/groups/999/export.csv").status_code == 404
    client.post("/api/auth/logout")
    assert anon_client.get(f"/api/groups/{group['id']}/export.csv").status_code == 401
