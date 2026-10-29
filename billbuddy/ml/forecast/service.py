"""Forecast for a group, calculated on the fly from its expenses.

No model is stored: the method only needs the expenses, so every new expense
is part of the next forecast immediately.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.expenses.models import Expense
from billbuddy.ml.forecast.model import Record

# "Today" in the users' time zone, not in the server's (which may be UTC)
TIMEZONE = ZoneInfo("Europe/Berlin")


def today() -> dt.date:
    return dt.datetime.now(TIMEZONE).date()


def group_records(session: Session, group_id: int) -> list[Record]:
    query = select(Expense.date, Expense.category, Expense.amount_cents).where(Expense.group_id == group_id)
    return [Record(date, category, amount) for date, category, amount in session.execute(query)]
