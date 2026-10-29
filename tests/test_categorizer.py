"""Tests for the categorizer: data preparation, model and training data."""

import datetime as dt

import pytest

from billbuddy.expenses import service as expenses
from billbuddy.expenses.categories import CATEGORIES
from billbuddy.ml.categorizer.model import MIN_CONFIDENCE, CategoryModel
from billbuddy.ml.categorizer.preprocessing import clean_description
from billbuddy.ml.categorizer.training_data import USER_WEIGHT, TrainingData, group_data, sample_data


@pytest.fixture(scope="module")
def model():
    data = sample_data()
    return CategoryModel.train(data.descriptions, data.amounts, data.categories, data.weights)


# --- Data preparation ---


@pytest.mark.parametrize(
    "raw, clean",
    [
        ("REWE Markt 34,50 Kartenzahlung", "rewe markt"),
        ("rewe", "rewe"),
        ("H&M", "h&m"),
        ("McDonald's", "mcdonald"),
        ("Booking.com", "booking com"),
        ("Filiale 123", ""),
    ],
)
def test_clean_description(raw, clean):
    assert clean_description(raw) == clean


# --- Training data ---


def test_sample_data_has_all_categories_and_no_duplicates():
    data = sample_data()
    assert set(data.categories) == set(CATEGORIES)
    assert len(data) > 500
    assert set(data.weights) == {1.0}


def test_group_data_uses_only_categorized_expenses(session):
    group = expenses.create_group(session, "Home", ["Anna"])
    anna = group.members[0]
    for description, category in [("Rewe", "Groceries"), ("Kino", "Leisure"), ("Irgendwas", None)]:
        expenses.create_expense(
            session,
            group.id,
            expenses.ExpenseInput(
                payer_id=anna.id,
                amount_cents=1250,
                date=dt.date(2026, 10, 29),
                description=description,
                participant_ids=[anna.id],
                category=category,
            ),
        )

    data = group_data(session, group.id)
    assert data.descriptions == ["Rewe", "Kino"]
    assert data.amounts == [12.5, 12.5]
    assert data.weights == [USER_WEIGHT, USER_WEIGHT]


# --- Model ---


@pytest.mark.parametrize(
    "description, amount, category",
    [
        ("Rewe 34,50", 34.5, "Groceries"),
        ("REWE Markt Kartenzahlung", 20, "Groceries"),
        ("Netflix", 13.99, "Subscriptions"),
        ("Miete November", 950, "Rent"),
        ("Aral Tankstelle", 60, "Transport"),
        ("Pizzeria Da Mario", 38, "Restaurants"),
        # Same word, different meaning: the model has to tell them apart
        ("Amazon", 45, "Shopping"),
        ("Amazon Prime", 8.99, "Subscriptions"),
    ],
)
def test_known_shops_are_recognized(model, description, amount, category):
    suggestion = model.suggest(description, amount)
    assert suggestion is not None
    assert suggestion.category == category
    assert suggestion.confidence >= MIN_CONFIDENCE


@pytest.mark.parametrize("description", ["xyz", "Filiale 123", ""])
def test_no_suggestion_when_unsure(model, description):
    assert model.suggest(description, 10) is None


def test_learns_from_user_categories():
    data = sample_data()
    before = CategoryModel.train(data.descriptions, data.amounts, data.categories, data.weights)
    assert before.suggest("Vereinsbeitrag Tennis", 15) is None  # unknown words: no suggestion

    corrections = TrainingData()
    for _ in range(2):
        corrections.add("Vereinsbeitrag Tennis", 15, "Leisure", USER_WEIGHT)
    combined = data + corrections
    after = CategoryModel.train(combined.descriptions, combined.amounts, combined.categories, combined.weights)

    assert after.suggest("Tennis Vereinsbeitrag", 15).category == "Leisure"
