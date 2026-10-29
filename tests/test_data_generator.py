"""Tests for the sample data generator in billbuddy.data."""

import csv
import datetime as dt

import pytest
from sqlalchemy import func, select

from billbuddy.data.generator import FIXED_COSTS, generate_expenses, load_into_db, write_csv
from billbuddy.expenses.categories import CATEGORIES
from billbuddy.expenses.models import Expense, Member

START = dt.date(2025, 11, 1)
END = dt.date(2026, 10, 31)


@pytest.fixture(scope="module")
def year():
    return generate_expenses(START, END)


def test_same_seed_gives_same_data():
    assert generate_expenses(START, END, seed=1) == generate_expenses(START, END, seed=1)
    assert generate_expenses(START, END, seed=1) != generate_expenses(START, END, seed=2)


def test_values_are_valid(year):
    assert all(START <= e.date <= END for e in year)
    assert all(e.amount_cents > 0 for e in year)
    assert all(e.category in CATEGORIES for e in year)
    assert {e.payer for e in year} == {"Anna", "Ben"}


def test_dates_are_sorted(year):
    assert [e.date for e in year] == sorted(e.date for e in year)


def test_every_fixed_cost_appears_once_per_month(year):
    fixed = [e for e in year if e.is_fixed]
    assert len(fixed) == 12 * len(FIXED_COSTS)
    rent_months = {e.date.month for e in fixed if e.category == "Rent"}
    assert rent_months == set(range(1, 13))


def test_contains_labelled_duplicates_and_outliers(year):
    duplicates = [e for e in year if e.is_duplicate]
    outliers = [e for e in year if e.is_outlier]
    assert duplicates and outliers
    # A duplicate has an identical original on the same day
    for dup in duplicates:
        assert any(
            not e.is_duplicate
            and (e.date, e.description, e.amount_cents) == (dup.date, dup.description, dup.amount_cents)
            for e in year
        )


def test_december_has_more_shopping_than_march():
    # Random data is noisy, so compare purchase counts over several seeds
    years = [e for seed in range(5) for e in generate_expenses(START, END, seed=seed)]

    def shopping(month):
        return sum(1 for e in years if e.category == "Shopping" and e.date.month == month)

    assert shopping(12) > 1.5 * shopping(3)


def test_write_csv(tmp_path, year):
    path = tmp_path / "expenses.csv"
    write_csv(year, path)

    with path.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(year)
    assert rows[0]["date"] == str(year[0].date)
    assert rows[0]["amount_cents"] == str(year[0].amount_cents)


def test_load_into_db(session, year):
    group = load_into_db(year, session)

    assert group.name == "Demo"
    assert session.scalar(select(func.count()).select_from(Member)) == 2
    assert session.scalar(select(func.count()).select_from(Expense)) == len(year)
    assert all(len(e.shares) == 2 for e in group.expenses)
