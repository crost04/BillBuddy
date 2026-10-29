"""Tests for the anomaly detection in billbuddy.ml.anomaly."""

import datetime as dt

from billbuddy.ml.anomaly.model import Entry, OutlierModel, duplicates_of, find_duplicates, find_outliers

DAY = dt.date(2026, 10, 15)


def entry(expense_id, description, amount_cents, days=0, category="Groceries"):
    return Entry(expense_id, DAY + dt.timedelta(days=days), description, amount_cents, category)


def groceries(n=20):
    """Typical grocery shopping between about 15 and 60 €."""
    amounts = [1500, 2200, 2800, 3300, 3800, 4500, 5200, 6100, 2500, 3500]
    return [entry(100 + i, "Rewe", amounts[i % len(amounts)], days=-2 * i - 3) for i in range(n)]


# --- Duplicates ---


def test_same_purchase_entered_twice_with_different_spelling():
    first = entry(1, "Rewe", 3450)
    second = entry(2, "REWE Kartenzahlung", 3450, days=1)
    assert duplicates_of(second, [first]) == [first]
    assert find_duplicates([first, second]) == [(first, second)]


def test_different_amount_or_far_apart_is_no_duplicate():
    first = entry(1, "Rewe", 3450)
    assert duplicates_of(entry(2, "Rewe", 3460), [first]) == []
    assert duplicates_of(entry(3, "Rewe", 3450, days=2), [first]) == []
    assert duplicates_of(entry(4, "Edeka", 3450), [first]) == []


def test_an_entry_is_no_duplicate_of_itself():
    first = entry(1, "Rewe", 3450)
    assert duplicates_of(first, [first]) == []


# --- Unusually high amounts ---


def test_typing_error_is_an_outlier():
    model = OutlierModel(groceries())
    check = model.check("Groceries", 34500)  # 345 € instead of 34,50 €
    assert check.is_outlier
    assert 3000 <= check.typical_cents <= 4000
    assert check.ratio > 8


def test_normal_and_somewhat_larger_amounts_are_fine():
    model = OutlierModel(groceries())
    assert not model.check("Groceries", 3600).is_outlier
    assert not model.check("Groceries", 7500).is_outlier  # a big shopping trip


def test_cheap_purchases_are_never_outliers():
    assert not OutlierModel(groceries()).check("Groceries", 150).is_outlier


def test_categories_with_little_data_are_not_checked():
    model = OutlierModel(groceries(5))
    assert not model.check("Groceries", 100000).is_outlier
    assert not model.check("Travel", 100000).is_outlier


def test_fixed_amounts_use_the_median():
    rent = [entry(200 + i, "Miete", 95000, days=-30 * i - 1, category="Rent") for i in range(10)]
    model = OutlierModel(rent)
    assert not model.check("Rent", 95000).is_outlier
    assert model.check("Rent", 950000).is_outlier  # one zero too many


def test_find_outliers_in_existing_entries():
    typo = entry(999, "Rewe", 38000)
    found = find_outliers([*groceries(), typo])
    assert [e for e, _ in found] == [typo]
