"""Tests for the database models in billbuddy.expenses."""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from billbuddy.expenses.models import Expense, ExpenseShare, Group, Member, SplitMethod


@pytest.fixture
def couple(session):
    group = Group(name="Home")
    anna = Member(name="Anna", monthly_income_cents=300_000)
    ben = Member(name="Ben", monthly_income_cents=200_000)
    group.members = [anna, ben]
    session.add(group)
    session.commit()
    return group, anna, ben


def make_expense(group, payer, members, amount_cents=3450, **kwargs):
    return Expense(
        group=group,
        payer=payer,
        amount_cents=amount_cents,
        date=dt.date(2026, 10, 29),
        description="Rewe",
        shares=[ExpenseShare(member=m) for m in members],
        **kwargs,
    )


def test_expense_with_shares_is_saved(session, couple):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [anna, ben]))
    session.commit()

    expense = session.scalars(select(Expense)).one()
    assert expense.payer.name == "Anna"
    assert expense.amount == Decimal("34.50")
    assert expense.split_method == SplitMethod.EQUAL
    assert expense.is_fixed is False
    assert expense.category is None
    assert {s.member.name for s in expense.shares} == {"Anna", "Ben"}


def test_expense_can_belong_to_a_subset_of_members(session, couple):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [ben]))
    session.commit()

    expense = session.scalars(select(Expense)).one()
    assert [s.member.name for s in expense.shares] == ["Ben"]


def test_percent_split_stores_percentages(session, couple):
    group, anna, ben = couple
    expense = make_expense(group, anna, [], split_method=SplitMethod.PERCENT)
    expense.shares = [
        ExpenseShare(member=anna, percent=60),
        ExpenseShare(member=ben, percent=40),
    ]
    session.add(expense)
    session.commit()

    assert sorted(s.percent for s in expense.shares) == [40, 60]


@pytest.mark.parametrize("amount_cents", [0, -100])
def test_amount_must_be_positive(session, couple, amount_cents):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [anna], amount_cents=amount_cents))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("percent", [0, 101])
def test_percent_must_be_between_0_and_100(session, couple, percent):
    group, anna, ben = couple
    expense = make_expense(group, anna, [], split_method=SplitMethod.PERCENT)
    expense.shares = [ExpenseShare(member=anna, percent=percent)]
    session.add(expense)
    with pytest.raises(IntegrityError):
        session.commit()


def test_member_cannot_take_part_twice(session, couple):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [ben, ben]))
    with pytest.raises(IntegrityError):
        session.commit()


def test_member_who_paid_cannot_be_deleted(session, couple):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [ben]))
    session.commit()

    session.delete(anna)
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_a_group_deletes_its_members_and_expenses(session, couple):
    group, anna, ben = couple
    session.add(make_expense(group, anna, [anna, ben]))
    session.commit()

    session.delete(group)
    session.commit()

    for model in (Group, Member, Expense, ExpenseShare):
        assert session.scalar(select(func.count()).select_from(model)) == 0
