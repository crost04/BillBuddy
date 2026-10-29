"""Tests for the business logic in billbuddy.expenses.service."""

import datetime as dt

import pytest

from billbuddy.expenses import service
from billbuddy.expenses.models import SplitMethod
from billbuddy.expenses.service import ExpenseInput, NotFoundError, ValidationError


@pytest.fixture
def flat(session):
    """A flat share with three members."""
    group = service.create_group(session, "Flat", ["Anna", "Ben", "Cem"])
    anna, ben, cem = group.members
    return group, anna, ben, cem


def expense_input(payer, participants, **kwargs):
    defaults = dict(amount_cents=3000, date=dt.date(2026, 10, 29), description="Rewe")
    return ExpenseInput(
        payer_id=payer.id,
        participant_ids=[m.id for m in participants],
        **{**defaults, **kwargs},
    )


def shares_of(expense):
    return {s.member.name: s.percent for s in expense.shares}


# --- Groups and members ---


def test_create_group_with_members(session):
    group = service.create_group(session, "Home", ["Anna", "Ben"])
    assert [m.name for m in group.members] == ["Anna", "Ben"]
    assert service.list_groups(session) == [group]


def test_member_names_must_be_unique(session, flat):
    group, *_ = flat
    with pytest.raises(ValidationError):
        service.add_member(session, group.id, "Anna")
    with pytest.raises(ValidationError):
        service.create_group(session, "Twins", ["Lea", "Lea"])


def test_update_member_income(session, flat):
    _, anna, *_ = flat
    service.update_member(session, anna.id, "Anna", 250_000)
    assert str(anna.monthly_income) == "2500"


def test_missing_group_raises_not_found(session):
    with pytest.raises(NotFoundError):
        service.get_group(session, 999)


def test_delete_group(session, flat):
    group, anna, ben, _ = flat
    service.create_expense(session, group.id, expense_input(anna, [anna, ben]))
    service.delete_group(session, group.id)
    assert service.list_groups(session) == []


# --- Expenses ---


def test_equal_split_between_all_members(session, flat):
    group, anna, ben, cem = flat
    expense = service.create_expense(session, group.id, expense_input(anna, [anna, ben, cem]))
    assert shares_of(expense) == {"Anna": None, "Ben": None, "Cem": None}
    assert expense.payer == anna


def test_expense_for_a_subset_of_members(session, flat):
    group, anna, ben, _ = flat
    expense = service.create_expense(session, group.id, expense_input(anna, [ben]))
    assert shares_of(expense) == {"Ben": None}


def test_percent_split(session, flat):
    group, anna, ben, _ = flat
    data = expense_input(anna, [anna, ben], split_method=SplitMethod.PERCENT, percents={anna.id: 70, ben.id: 30})
    expense = service.create_expense(session, group.id, data)
    assert shares_of(expense) == {"Anna": 70, "Ben": 30}


@pytest.mark.parametrize(
    "percents",
    [
        {"Anna": 60, "Ben": 30},  # adds up to 90
        {"Anna": 100},  # Ben is missing
        {"Anna": 110, "Ben": -10},  # negative
    ],
)
def test_invalid_percentages_are_rejected(session, flat, percents):
    group, anna, ben, cem = flat
    by_name = {"Anna": anna, "Ben": ben, "Cem": cem}
    data = expense_input(
        anna,
        [anna, ben],
        split_method=SplitMethod.PERCENT,
        percents={by_name[n].id: p for n, p in percents.items()},
    )
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, data)


def test_income_split_is_a_snapshot(session, flat):
    group, anna, ben, _ = flat
    service.update_member(session, anna.id, "Anna", 300_000)
    service.update_member(session, ben.id, "Ben", 200_000)

    data = expense_input(anna, [anna, ben], split_method=SplitMethod.INCOME)
    expense = service.create_expense(session, group.id, data)
    assert shares_of(expense) == pytest.approx({"Anna": 60, "Ben": 40})

    # A later raise does not change the old expense
    service.update_member(session, ben.id, "Ben", 300_000)
    assert shares_of(expense) == pytest.approx({"Anna": 60, "Ben": 40})


def test_income_split_needs_incomes(session, flat):
    group, anna, ben, _ = flat
    data = expense_input(anna, [anna, ben], split_method=SplitMethod.INCOME)
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, data)


@pytest.mark.parametrize(
    "changes",
    [
        {"amount_cents": 0},
        {"description": "   "},
        {"category": "Unicorns"},
    ],
)
def test_invalid_values_are_rejected(session, flat, changes):
    group, anna, ben, _ = flat
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, expense_input(anna, [anna, ben], **changes))


def test_payer_and_participants_must_belong_to_the_group(session, flat):
    group, anna, ben, _ = flat
    other = service.create_group(session, "Other", ["Zoe"])
    zoe = other.members[0]

    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, expense_input(zoe, [anna]))
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, expense_input(anna, [zoe]))
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, expense_input(anna, []))
    with pytest.raises(ValidationError):
        service.create_expense(session, group.id, expense_input(anna, [ben, ben]))


def test_update_expense_replaces_values_and_shares(session, flat):
    group, anna, ben, cem = flat
    expense = service.create_expense(session, group.id, expense_input(anna, [anna, ben]))

    data = expense_input(
        ben,
        [ben, cem],
        amount_cents=5000,
        category="Groceries",
        split_method=SplitMethod.PERCENT,
        percents={ben.id: 50, cem.id: 50},
    )
    updated = service.update_expense(session, expense.id, data)

    assert updated.payer == ben
    assert updated.amount_cents == 5000
    assert updated.category == "Groceries"
    assert shares_of(updated) == {"Ben": 50, "Cem": 50}


def test_list_expenses_newest_first_and_by_date_range(session, flat):
    group, anna, ben, _ = flat
    for day in (1, 15, 31):
        service.create_expense(session, group.id, expense_input(anna, [anna, ben], date=dt.date(2026, 10, day)))
    service.create_expense(session, group.id, expense_input(anna, [anna], date=dt.date(2026, 11, 2)))

    all_dates = [e.date.day for e in service.list_expenses(session, group.id)]
    assert all_dates == [2, 31, 15, 1]

    october = service.list_expenses(session, group.id, dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    assert [e.date.day for e in october] == [31, 15, 1]


def test_delete_expense(session, flat):
    group, anna, ben, _ = flat
    expense = service.create_expense(session, group.id, expense_input(anna, [anna, ben]))
    service.delete_expense(session, expense.id)
    with pytest.raises(NotFoundError):
        service.get_expense(session, expense.id)
