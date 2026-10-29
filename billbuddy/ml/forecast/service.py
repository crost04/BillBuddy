"""Forecast for a group, calculated on the fly from its expenses.

No model is stored: the method only needs the expenses, so every new expense
is part of the next forecast immediately.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.clock import today  # noqa: F401 (used by the API, replaced in tests)
from billbuddy.expenses.models import Expense
from billbuddy.ml.forecast.model import Record


def group_records(session: Session, group_id: int) -> list[Record]:
    query = select(Expense.date, Expense.category, Expense.amount_cents).where(Expense.group_id == group_id)
    return [Record(date, category, amount) for date, category, amount in session.execute(query)]
