"""Tests for billbuddy.settlement.service (with a database)."""

import datetime as dt

import pytest

from billbuddy.expenses import service as expenses
from billbuddy.expenses.service import ExpenseInput, NotFoundError, ValidationError
from billbuddy.settlement import service
from billbuddy.settlement.calculator import Transfer

TODAY = dt.date(2026, 10, 29)


@pytest.fixture
def flat(session):
    group = expenses.create_group(session, "Flat", ["Anna", "Ben", "Cem"])
    return (group, *group.members)


def add_expense(session, group, payer, amount_cents, participants):
    data = ExpenseInput(
        payer_id=payer.id,
        amount_cents=amount_cents,
        date=TODAY,
        description="Rewe",
        participant_ids=[m.id for m in participants],
    )
    return expenses.create_expense(session, group.id, data)


def test_settlement_of_a_new_group_is_empty(session, flat):
    group, anna, ben, cem = flat
    settlement = service.get_settlement(session, group.id)
    assert settlement.balances == {anna.id: 0, ben.id: 0, cem.id: 0}
    assert settlement.transfers == []


def test_settlement_after_expenses(session, flat):
    group, anna, ben, cem = flat
    add_expense(session, group, anna, 9000, [anna, ben, cem])  # Ben and Cem owe Anna 30 each
    add_expense(session, group, ben, 3000, [ben, cem])  # Cem owes Ben 15

    settlement = service.get_settlement(session, group.id)
    assert settlement.balances == {anna.id: 6000, ben.id: -1500, cem.id: -4500}
    assert settlement.transfers == [Transfer(cem.id, anna.id, 4500), Transfer(ben.id, anna.id, 1500)]


def test_recorded_payment_settles_the_debt(session, flat):
    group, anna, ben, cem = flat
    add_expense(session, group, anna, 6000, [anna, ben])

    service.create_payment(session, group.id, ben.id, anna.id, 3000, TODAY)

    settlement = service.get_settlement(session, group.id)
    assert set(settlement.balances.values()) == {0}
    assert settlement.transfers == []


def test_list_and_delete_payments(session, flat):
    group, anna, ben, cem = flat
    older = service.create_payment(session, group.id, ben.id, anna.id, 1000, dt.date(2026, 10, 1))
    newer = service.create_payment(session, group.id, cem.id, anna.id, 2000, dt.date(2026, 10, 20))

    assert service.list_payments(session, group.id) == [newer, older]

    service.delete_payment(session, older.id)
    assert service.list_payments(session, group.id) == [newer]
    with pytest.raises(NotFoundError):
        service.delete_payment(session, older.id)


def test_invalid_payments_are_rejected(session, flat):
    group, anna, ben, cem = flat
    zoe = expenses.create_group(session, "Other", ["Zoe"]).members[0]

    with pytest.raises(ValidationError):
        service.create_payment(session, group.id, anna.id, anna.id, 1000, TODAY)
    with pytest.raises(ValidationError):
        service.create_payment(session, group.id, zoe.id, anna.id, 1000, TODAY)
    with pytest.raises(ValidationError):
        service.create_payment(session, group.id, ben.id, anna.id, 0, TODAY)


def test_deleting_a_group_deletes_its_payments(session, flat):
    group, anna, ben, cem = flat
    add_expense(session, group, anna, 6000, [anna, ben])
    service.create_payment(session, group.id, ben.id, anna.id, 3000, TODAY)

    expenses.delete_group(session, group.id)
    assert expenses.list_groups(session) == []
