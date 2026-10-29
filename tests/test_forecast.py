"""Tests for the month-end forecast in billbuddy.ml.forecast."""

import datetime as dt

import pytest

from billbuddy.ml.forecast import service as forecast_service
from billbuddy.ml.forecast.model import Record, forecast_month


def monthly_pattern(months, extra=()):
    """The same fixed costs every month: rent on the 1st, a subscription on the 20th."""
    records = []
    for year, month in months:
        records.append(Record(dt.date(year, month, 1), "Rent", 100_000))
        records.append(Record(dt.date(year, month, 20), "Subscriptions", 1_000))
    return records + list(extra)


# Group started in March (partial month), April–September are complete history months
HISTORY = [(2026, m) for m in range(3, 10)]


def test_history_is_the_last_six_complete_months():
    records = monthly_pattern(HISTORY + [(2026, 10)])
    result = forecast_month(records, today=dt.date(2026, 10, 15))

    assert result.is_current
    # March is left out: the group started then, so it is probably not a complete month
    assert result.history_months == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    # The subscription entered in advance for the 20th does not count as spent yet
    assert result.total.spent_cents == 100_000
    assert result.total.forecast_cents == 101_000


def test_forecast_counts_only_expenses_until_today():
    records = monthly_pattern(HISTORY) + [Record(dt.date(2026, 10, 1), "Rent", 100_000)]
    total = forecast_month(records, today=dt.date(2026, 10, 15)).total

    assert total.spent_cents == 100_000
    assert total.forecast_cents == 101_000  # + the subscription that is still due
    assert total.low_cents == total.high_cents == 101_000  # every month was the same
    assert total.average_cents == 101_000


def test_no_extrapolation_trap_at_the_start_of_the_month():
    # "spent / day × days" would turn the rent on the 1st into 31 × 1000 €
    records = monthly_pattern(HISTORY) + [Record(dt.date(2026, 10, 1), "Rent", 100_000)]
    assert forecast_month(records, today=dt.date(2026, 10, 1)).total.forecast_cents == 101_000


def test_categories_that_are_still_due_appear_with_zero_spent():
    records = monthly_pattern(HISTORY) + [Record(dt.date(2026, 10, 1), "Rent", 100_000)]
    rows = {f.category: f for f in forecast_month(records, today=dt.date(2026, 10, 15)).categories}

    assert rows["Subscriptions"].spent_cents == 0
    assert rows["Subscriptions"].forecast_cents == 1_000
    assert rows["Rent"].forecast_cents == 100_000
    # Sorted by forecast, largest first
    assert [f.category for f in forecast_month(records, today=dt.date(2026, 10, 15)).categories] == [
        "Rent",
        "Subscriptions",
    ]


def test_median_is_robust_against_one_unusual_month():
    holiday = Record(dt.date(2026, 8, 25), "Travel", 200_000)
    records = monthly_pattern(HISTORY, extra=[holiday]) + [Record(dt.date(2026, 10, 1), "Rent", 100_000)]
    total = forecast_month(records, today=dt.date(2026, 10, 15)).total

    assert total.forecast_cents == 101_000  # the holiday does not move the forecast
    assert total.low_cents <= total.forecast_cents < total.high_cents  # but widens the range


def test_without_history_there_is_no_forecast():
    # Only the first (partial) month and the current month: nothing to learn from yet
    records = monthly_pattern([(2026, 9), (2026, 10)])
    result = forecast_month(records, today=dt.date(2026, 10, 15))

    assert result.history_months == []
    assert result.total.spent_cents == 100_000
    assert result.total.forecast_cents is None
    assert result.total.average_cents is None


def test_past_month_shows_the_real_total_and_the_usual_average():
    records = monthly_pattern(HISTORY + [(2026, 10)])
    result = forecast_month(records, today=dt.date(2026, 11, 5), month="2026-09")

    assert not result.is_current
    assert result.day == 30
    assert result.total.spent_cents == 101_000
    assert result.total.forecast_cents is None
    assert result.total.average_cents == 101_000


def test_empty_data():
    result = forecast_month([], today=dt.date(2026, 10, 15))
    assert result.total.spent_cents == 0
    assert result.categories == []


# --- API: overview screen ---


@pytest.fixture
def group(client, monkeypatch):
    monkeypatch.setattr(forecast_service, "today", lambda: dt.date(2026, 10, 15))
    group = client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()
    anna, ben = group["members"]
    # March (first, partial month) to September as history, then October so far
    for month in range(3, 11):
        add(client, group, anna, f"2026-{month:02d}-01", 1000, "Rent")
        if month < 10:
            add(client, group, ben, f"2026-{month:02d}-20", 10, "Subscriptions")
    return group


def add(client, group, payer, date, amount, category):
    response = client.post(
        f"/api/groups/{group['id']}/expenses",
        json={
            "payer_id": payer["id"],
            "amount": amount,
            "date": date,
            "description": category,
            "category": category,
            "participants": [{"member_id": m["id"]} for m in group["members"]],
        },
    )
    assert response.status_code == 201


def test_overview_of_the_current_month(client, group):
    body = client.get(f"/api/groups/{group['id']}/overview").json()

    assert (body["month"], body["is_current"], body["day"], body["days_in_month"]) == ("2026-10", True, 15, 31)
    assert body["history_months"] == 6
    assert body["total"] == {
        "category": None,
        "spent": 1000.0,
        "forecast": 1010.0,
        "low": 1010.0,
        "high": 1010.0,
        "average": 1010.0,
    }
    assert [(c["category"], c["spent"], c["forecast"]) for c in body["categories"]] == [
        ("Rent", 1000.0, 1000.0),
        ("Subscriptions", 0.0, 10.0),
    ]
    anna, ben = group["members"]
    assert body["members"] == [{"member_id": anna["id"], "paid": 1000.0}, {"member_id": ben["id"], "paid": 0.0}]
    assert [h["month"] for h in body["history"]] == [f"2026-{m:02d}" for m in range(4, 11)]
    assert body["history"][-1]["total"] == 1000.0


def test_overview_of_a_past_month(client, group):
    body = client.get(f"/api/groups/{group['id']}/overview", params={"month": "2026-09"}).json()
    assert not body["is_current"]
    assert body["total"]["spent"] == 1010.0
    assert body["total"]["forecast"] is None


def test_overview_needs_access(client, anon_client, group):
    assert client.get("/api/groups/999/overview").status_code == 404
    client.post("/api/auth/logout")
    assert anon_client.get(f"/api/groups/{group['id']}/overview").status_code == 401
