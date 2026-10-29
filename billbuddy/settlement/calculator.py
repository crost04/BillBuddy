"""Pure calculations for splitting expenses and settling debts.

No database access here: the functions only take numbers and model objects,
which makes them easy to test and to reason about.
"""

import math
from dataclasses import dataclass

from billbuddy.expenses.models import Expense


@dataclass(frozen=True)
class Transfer:
    from_member_id: int
    to_member_id: int
    amount_cents: int


def split_amount(amount_cents: int, weights: dict[int, float]) -> dict[int, int]:
    """Split an amount in proportion to the weights, exact to the cent.

    Rounding every part on its own could lose or add a cent (10.00 € / 3).
    Instead every part is rounded down and the leftover cents go to the parts
    with the largest remainders ("largest remainder method"). On a tie the
    member with the lower id gets the cent, so the result is always the same.
    """
    total = sum(weights.values())
    exact = {key: amount_cents * weight / total for key, weight in weights.items()}
    parts = {key: math.floor(value) for key, value in exact.items()}

    leftover = amount_cents - sum(parts.values())
    by_remainder = sorted(exact, key=lambda key: (-(exact[key] - parts[key]), key))
    for key in by_remainder[:leftover]:
        parts[key] += 1
    return parts


def expense_shares(expense: Expense) -> dict[int, int]:
    """How many cents each participant of an expense has to carry."""
    # Equal split: every share has weight 1. Percent and income: the stored percentage.
    weights = {s.member_id: s.percent if s.percent is not None else 1 for s in expense.shares}
    return split_amount(expense.amount_cents, weights)


def compute_balances(member_ids, expenses, payments) -> dict[int, int]:
    """Balance per member in cents.

    Positive: the member gets money back. Negative: the member owes money.
    All balances together always add up to 0.
    """
    balances = {member_id: 0 for member_id in member_ids}
    for expense in expenses:
        balances[expense.payer_id] += expense.amount_cents
        for member_id, cents in expense_shares(expense).items():
            balances[member_id] -= cents
    for payment in payments:
        balances[payment.from_member_id] += payment.amount_cents
        balances[payment.to_member_id] -= payment.amount_cents
    return balances


def minimal_transfers(balances: dict[int, int]) -> list[Transfer]:
    """Transfers that bring every balance to 0.

    Greedy approach: the member who owes the most pays the member who gets the
    most, until everyone is even. This needs at most n-1 transfers for n
    members. Finding the absolute minimum is an NP-hard problem; for groups of
    this size the greedy result is optimal or very close to it.
    """
    debtors = {m: -b for m, b in balances.items() if b < 0}
    creditors = {m: b for m, b in balances.items() if b > 0}
    transfers = []

    while debtors and creditors:
        debtor = max(debtors, key=lambda m: (debtors[m], -m))
        creditor = max(creditors, key=lambda m: (creditors[m], -m))
        amount = min(debtors[debtor], creditors[creditor])
        transfers.append(Transfer(debtor, creditor, amount))

        debtors[debtor] -= amount
        creditors[creditor] -= amount
        if debtors[debtor] == 0:
            del debtors[debtor]
        if creditors[creditor] == 0:
            del creditors[creditor]

    return transfers
