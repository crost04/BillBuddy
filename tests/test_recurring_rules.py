"""Tests for standing orders (fixed costs entered automatically every month)."""

import datetime as dt

import pytest

from billbuddy.expenses import recurring_rules, service
from billbuddy.expenses.models import Expense, SplitMethod
from billbuddy.expenses.recurring_rules import add_month, without_month_names
from billbuddy.expenses.service import ExpenseInput, ValidationError


@pytest.fixture
def home(session):
    group = service.create_group(session, "Home", ["Anna", "Ben"])
    return (group, *group.members)


def add(session, group, payer, description, amount_cents, date, **kwargs):
    data = ExpenseInput(
        payer_id=payer.id,
        amount_cents=amount_cents,
        date=date,
        description=description,
        participant_ids=[m.id for m in group.members],
        **kwargs,
    )
    return service.create_expense(session, group.id, data)


def expenses_of(session, group):
    return sorted(session.query(Expense).filter_by(group_id=group.id), key=lambda e: (e.date, e.id))


@pytest.mark.parametrize(
    "description, cleaned",
    [("Miete Oktober", "Miete"), ("Netflix", "Netflix"), ("Strom Sept 2026", "Strom 2026"), ("Oktober", "Oktober")],
)
def test_without_month_names(description, cleaned):
    assert without_month_names(description) == cleaned


@pytest.mark.parametrize(
    "date, day, expected",
    [
        (dt.date(2026, 10, 1), 1, dt.date(2026, 11, 1)),
        (dt.date(2026, 12, 15), 15, dt.date(2027, 1, 15)),
        (dt.date(2027, 1, 31), 31, dt.date(2027, 2, 28)),  # February is shorter
        (dt.date(2027, 2, 28), 31, dt.date(2027, 3, 31)),  # and back to the 31st
    ],
)
def test_add_month(date, day, expected):
    assert add_month(date, day) == expected


def test_rule_is_a_copy_of_the_expense(session, home):
    group, anna, ben = home
    rent = add(
        session,
        group,
        anna,
        "Miete Oktober",
        95000,
        dt.date(2026, 10, 1),
        category="Rent",
        split_method=SplitMethod.PERCENT,
        percents={anna.id: 60, ben.id: 40},
    )

    rule = recurring_rules.create_from_expense(session, group.id, rent.id)

    assert (rule.description, rule.amount_cents, rule.category, rule.payer_id) == ("Miete", 95000, "Rent", anna.id)
    assert rule.split_method == "percent"
    assert sorted(p["percent"] for p in rule.participants) == [40, 60]
    assert (rule.day_of_month, rule.next_date) == (1, dt.date(2026, 11, 1))
    assert rent.is_fixed and rent.recurring_rule_id == rule.id


def test_due_entries_are_booked_and_missed_months_caught_up(session, home):
    group, anna, ben = home
    netflix = add(session, group, ben, "Netflix", 1399, dt.date(2026, 8, 10), category="Subscriptions")
    recurring_rules.create_from_expense(session, group.id, netflix.id)

    assert recurring_rules.book_due(session, group.id, today=dt.date(2026, 9, 9)) == 0
    # Nobody opened the app for a while: September and October are booked together
    assert recurring_rules.book_due(session, group.id, today=dt.date(2026, 10, 29)) == 2

    entries = expenses_of(session, group)
    assert [e.date for e in entries] == [dt.date(2026, 8, 10), dt.date(2026, 9, 10), dt.date(2026, 10, 10)]
    assert all(e.is_fixed and e.payer_id == ben.id and e.category == "Subscriptions" for e in entries)
    assert all(len(e.shares) == 2 for e in entries)


def test_booking_twice_creates_nothing_new(session, home):
    group, anna, ben = home
    rent = add(session, group, anna, "Miete", 95000, dt.date(2026, 9, 1))
    recurring_rules.create_from_expense(session, group.id, rent.id)

    recurring_rules.book_due(session, group.id, today=dt.date(2026, 10, 29))
    recurring_rules.book_due(session, group.id, today=dt.date(2026, 10, 29))

    assert len(expenses_of(session, group)) == 2


def test_new_amount_applies_to_future_entries(session, home):
    group, anna, ben = home
    rent = add(session, group, anna, "Miete", 95000, dt.date(2026, 9, 1))
    rule = recurring_rules.create_from_expense(session, group.id, rent.id)

    recurring_rules.update_amount(session, rule, 99000)
    recurring_rules.book_due(session, group.id, today=dt.date(2026, 10, 1))

    assert [e.amount_cents for e in expenses_of(session, group)] == [95000, 99000]
    with pytest.raises(ValidationError):
        recurring_rules.update_amount(session, rule, 0)


def test_stopped_rule_books_nothing_and_keeps_old_entries(session, home):
    group, anna, ben = home
    rent = add(session, group, anna, "Miete", 95000, dt.date(2026, 9, 1))
    rule = recurring_rules.create_from_expense(session, group.id, rent.id)

    recurring_rules.delete_rule(session, rule)
    assert recurring_rules.book_due(session, group.id, today=dt.date(2026, 12, 1)) == 0
    assert len(expenses_of(session, group)) == 1


def test_same_expense_cannot_become_two_rules(session, home):
    group, anna, ben = home
    rent = add(session, group, anna, "Miete", 95000, dt.date(2026, 9, 1))
    recurring_rules.create_from_expense(session, group.id, rent.id)
    with pytest.raises(ValidationError):
        recurring_rules.create_from_expense(session, group.id, rent.id)


def test_expense_of_another_group_is_rejected(session, home):
    group, anna, ben = home
    other = service.create_group(session, "Other", ["Zoe"])
    foreign = add(session, other, other.members[0], "Miete", 50000, dt.date(2026, 9, 1))
    with pytest.raises(ValidationError):
        recurring_rules.create_from_expense(session, group.id, foreign.id)


def test_deleting_the_group_deletes_its_rules(session, home):
    group, anna, ben = home
    rent = add(session, group, anna, "Miete", 95000, dt.date(2026, 9, 1))
    recurring_rules.create_from_expense(session, group.id, rent.id)
    service.delete_group(session, group.id)
    assert recurring_rules.list_rules(session, group.id) == []
