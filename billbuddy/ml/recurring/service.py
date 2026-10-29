"""Recurring costs of a group, calculated on the fly from its expenses."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.clock import today
from billbuddy.expenses.models import Expense, RecurringDismissal
from billbuddy.ml.recurring.model import Item, RecurringSeries, description_key, find_recurring


def group_items(session: Session, group_id: int) -> list[Item]:
    query = select(Expense.id, Expense.date, Expense.description, Expense.amount_cents, Expense.is_fixed).where(
        Expense.group_id == group_id
    )
    return [Item(*row) for row in session.execute(query)]


def group_series(session: Session, group_id: int) -> list[RecurringSeries]:
    """Recognized series, without those the group said are no fixed costs."""
    dismissed = set(session.scalars(select(RecurringDismissal.key).where(RecurringDismissal.group_id == group_id)))
    return [s for s in find_recurring(group_items(session, group_id), today()) if s.key not in dismissed]


def dismiss(session: Session, group_id: int, key: str) -> None:
    """Remember that this description is no fixed cost, so it is not suggested again."""
    exists = session.scalar(
        select(RecurringDismissal).where(RecurringDismissal.group_id == group_id, RecurringDismissal.key == key)
    )
    if not exists:
        session.add(RecurringDismissal(group_id=group_id, key=key))
        session.commit()


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
