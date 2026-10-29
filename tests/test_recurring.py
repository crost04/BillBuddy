"""Tests for the recurring-cost detection in billbuddy.ml.recurring."""

import datetime as dt

import pytest

from billbuddy.ml.recurring.model import Item, description_key, find_recurring

TODAY = dt.date(2026, 10, 29)


def monthly(description, amount_cents, day, months=range(4, 11), year=2026, is_fixed=False):
    return [Item(None, dt.date(year, m, day), description, amount_cents, is_fixed) for m in months]


@pytest.mark.parametrize(
    "description, key",
    [
        ("Miete Oktober", "miete"),
        ("MIETE November", "miete"),
        ("Netflix 13,99", "netflix"),
        ("Amazon Prime", "amazon prime"),
    ],
)
def test_description_key(description, key):
    assert description_key(description) == key


def test_monthly_subscription_is_found():
    [series] = find_recurring(monthly("Netflix", 1399, 10), TODAY)

    assert series.key == "netflix"
    assert series.count == 7
    assert series.typical_amount_cents == 1399
    assert series.day_of_month == 10
    assert 28 <= series.interval_days <= 31
    assert series.last_date == dt.date(2026, 10, 10)
    assert series.next_date == dt.date(2026, 11, 10)
    assert series.active
    assert not series.already_fixed


def test_rent_with_changing_month_name_is_one_series():
    months = [(7, "Juli"), (8, "August"), (9, "September"), (10, "Oktober")]
    items = [Item(None, dt.date(2026, m, 1), f"Miete {name}", 95000) for m, name in months]
    [series] = find_recurring(items, TODAY)
    assert series.key == "miete"
    assert series.description == "Miete Oktober"


def test_small_date_shifts_and_price_changes_are_allowed():
    # Paid on the next working day; the electricity price went up a little
    days = [1, 3, 1, 2, 1, 4, 1]
    amounts = [8500, 8500, 8500, 8500, 8900, 8900, 8900]
    items = [
        Item(None, dt.date(2026, m, d), "Stadtwerke Strom", a) for m, d, a in zip(range(4, 11), days, amounts)
    ]
    assert len(find_recurring(items, TODAY)) == 1


def test_weekly_groceries_are_not_fixed_costs():
    start = dt.date(2026, 9, 1)
    items = [Item(None, start + dt.timedelta(days=7 * w), "Rewe", 3000 + 700 * (w % 3)) for w in range(8)]
    assert find_recurring(items, TODAY) == []


def test_monthly_but_very_different_amounts_are_not_fixed_costs():
    amounts = [2000, 8000, 3500, 12000, 2500]
    items = [Item(None, dt.date(2026, m, 15), "Amazon", a) for m, a in zip(range(6, 11), amounts)]
    assert find_recurring(items, TODAY) == []


def test_two_payments_are_not_enough():
    assert find_recurring(monthly("Spotify", 1799, 20, months=[9, 10]), TODAY) == []


def test_cancelled_subscription_is_inactive():
    [series] = find_recurring(monthly("Fitnessstudio", 2990, 3, months=range(1, 6)), TODAY)
    assert not series.active


def test_already_marked_series():
    [series] = find_recurring(monthly("Spotify", 1799, 20, is_fixed=True), TODAY)
    assert series.already_fixed


def test_series_are_sorted_by_amount():
    items = monthly("Netflix", 1399, 10) + monthly("Miete", 95000, 1)
    assert [s.key for s in find_recurring(items, TODAY)] == ["miete", "netflix"]
