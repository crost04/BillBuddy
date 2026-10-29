"""Recurring costs of a group, calculated on the fly from its expenses."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.clock import today
from billbuddy.expenses.models import Expense
from billbuddy.ml.recurring.model import Item, RecurringSeries, description_key, find_recurring


def group_items(session: Session, group_id: int) -> list[Item]:
    query = select(Expense.id, Expense.date, Expense.description, Expense.amount_cents, Expense.is_fixed).where(
        Expense.group_id == group_id
    )
    return [Item(*row) for row in session.execute(query)]


def group_series(session: Session, group_id: int) -> list[RecurringSeries]:
    return find_recurring(group_items(session, group_id), today())


def mark_fixed(session: Session, group_id: int, key: str) -> int:
    """Mark every expense of the series as fixed cost; returns how many were changed."""
    expenses = session.scalars(select(Expense).where(Expense.group_id == group_id, Expense.is_fixed.is_(False)))
    changed = 0
    for expense in expenses:
        if description_key(expense.description) == key:
            expense.is_fixed = True
            changed += 1
    session.commit()
    return changed
