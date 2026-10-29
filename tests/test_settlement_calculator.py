"""Tests for the pure calculations in billbuddy.settlement.calculator."""

import random

import pytest

from billbuddy.expenses.models import Expense, ExpenseShare, Payment
from billbuddy.settlement.calculator import (
    Transfer,
    compute_balances,
    expense_shares,
    minimal_transfers,
    split_amount,
)

ANNA, BEN, CEM, DIA = 1, 2, 3, 4


def expense(payer, amount_cents, participants):
    """participants: list of member ids, or {member_id: percent}."""
    if isinstance(participants, dict):
        shares = [ExpenseShare(member_id=m, percent=p) for m, p in participants.items()]
    else:
        shares = [ExpenseShare(member_id=m) for m in participants]
    return Expense(payer_id=payer, amount_cents=amount_cents, shares=shares)


# --- split_amount ---


def test_split_equally():
    assert split_amount(3000, {ANNA: 1, BEN: 1}) == {ANNA: 1500, BEN: 1500}


def test_split_never_loses_a_cent():
    # 10.00 € / 3 = 3.333... -> one person pays the extra cent
    assert split_amount(1000, {ANNA: 1, BEN: 1, CEM: 1}) == {ANNA: 334, BEN: 333, CEM: 333}


def test_split_by_percent():
    assert split_amount(1001, {ANNA: 60, BEN: 40}) == {ANNA: 601, BEN: 400}


@pytest.mark.parametrize("seed", range(20))
def test_parts_always_add_up_to_the_amount(seed):
    rng = random.Random(seed)
    amount = rng.randint(1, 100_000)
    weights = {m: rng.uniform(1, 100) for m in range(rng.randint(1, 6))}
    assert sum(split_amount(amount, weights).values()) == amount


# --- expense_shares ---


def test_expense_shares_equal_and_subset():
    assert expense_shares(expense(ANNA, 900, [ANNA, BEN, CEM])) == {ANNA: 300, BEN: 300, CEM: 300}
    assert expense_shares(expense(ANNA, 900, [BEN])) == {BEN: 900}


def test_expense_shares_percent():
    assert expense_shares(expense(ANNA, 10000, {ANNA: 70, BEN: 30})) == {ANNA: 7000, BEN: 3000}


# --- compute_balances ---


def test_balances_of_a_couple():
    expenses = [
        expense(ANNA, 6000, [ANNA, BEN]),  # Ben owes Anna 30
        expense(BEN, 2000, [ANNA, BEN]),  # Anna owes Ben 10
    ]
    assert compute_balances([ANNA, BEN], expenses, []) == {ANNA: 2000, BEN: -2000}


def test_payment_reduces_debt():
    expenses = [expense(ANNA, 6000, [ANNA, BEN])]
    payments = [Payment(from_member_id=BEN, to_member_id=ANNA, amount_cents=3000)]
    assert compute_balances([ANNA, BEN], expenses, payments) == {ANNA: 0, BEN: 0}


def test_member_without_expenses_has_zero_balance():
    balances = compute_balances([ANNA, BEN, CEM], [expense(ANNA, 1000, [ANNA, BEN])], [])
    assert balances[CEM] == 0


@pytest.mark.parametrize("seed", range(20))
def test_balances_always_add_up_to_zero(seed):
    rng = random.Random(seed)
    members = [ANNA, BEN, CEM, DIA]
    expenses = [
        expense(rng.choice(members), rng.randint(1, 50_000), rng.sample(members, rng.randint(1, 4)))
        for _ in range(30)
    ]
    assert sum(compute_balances(members, expenses, []).values()) == 0


# --- minimal_transfers ---


def test_no_transfers_when_everyone_is_even():
    assert minimal_transfers({ANNA: 0, BEN: 0}) == []


def test_one_transfer_for_a_couple():
    assert minimal_transfers({ANNA: 2000, BEN: -2000}) == [Transfer(BEN, ANNA, 2000)]


def test_two_debtors_pay_one_creditor():
    transfers = minimal_transfers({ANNA: 3000, BEN: -1000, CEM: -2000})
    assert transfers == [Transfer(CEM, ANNA, 2000), Transfer(BEN, ANNA, 1000)]


@pytest.mark.parametrize("seed", range(20))
def test_transfers_settle_everything_with_at_most_n_minus_1(seed):
    rng = random.Random(seed)
    members = [ANNA, BEN, CEM, DIA]
    expenses = [
        expense(rng.choice(members), rng.randint(1, 50_000), rng.sample(members, rng.randint(1, 4)))
        for _ in range(30)
    ]
    balances = compute_balances(members, expenses, [])
    transfers = minimal_transfers(balances)

    assert len(transfers) <= len(members) - 1
    payments = [
        Payment(from_member_id=t.from_member_id, to_member_id=t.to_member_id, amount_cents=t.amount_cents)
        for t in transfers
    ]
    assert set(compute_balances(members, expenses, payments).values()) == {0}
