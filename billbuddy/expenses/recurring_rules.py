"""Standing orders: fixed costs that are entered automatically every month.

The free server has no scheduler that could run at night. So due entries are
booked whenever someone of the group opens the app (book_due is called by the
API before expenses, balances or the overview are shown). Months that were
missed in the meantime are booked as well, with their correct dates.
"""

import calendar
import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from billbuddy.expenses.models import Expense, ExpenseShare, RecurringRule, SplitMethod
from billbuddy.expenses.service import ValidationError, get_expense
from billbuddy.ml.recurring.model import MONTH_WORDS

_MONTH_PATTERN = re.compile(r"\b(" + "|".join(sorted(MONTH_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)


def without_month_names(description: str) -> str:
    """'Miete Oktober' -> 'Miete', so the next entries do not all say 'Oktober'."""
    cleaned = " ".join(_MONTH_PATTERN.sub(" ", description).split())
    return cleaned or description


def add_month(date: dt.date, day_of_month: int) -> dt.date:
    """The same day one month later; the 31st becomes the last day of shorter months."""
    year, month = (date.year + 1, 1) if date.month == 12 else (date.year, date.month + 1)
    return dt.date(year, month, min(day_of_month, calendar.monthrange(year, month)[1]))


def create_from_expense(session: Session, group_id: int, expense_id: int) -> RecurringRule:
    """Turn an expense into a standing order that starts one month after it."""
    expense = get_expense(session, expense_id)
    if expense.group_id != group_id:
        raise ValidationError("The expense does not belong to this group")
    if expense.recurring_rule_id is not None and session.get(RecurringRule, expense.recurring_rule_id):
        raise ValidationError("This expense is already entered automatically every month")

    rule = RecurringRule(
        group_id=group_id,
        payer_id=expense.payer_id,
        description=without_month_names(expense.description),
        amount_cents=expense.amount_cents,
        category=expense.category,
        split_method=expense.split_method.value,
        participants=[{"member_id": s.member_id, "percent": s.percent} for s in expense.shares],
        day_of_month=expense.date.day,
        next_date=add_month(expense.date, expense.date.day),
    )
    session.add(rule)
    session.flush()
    expense.is_fixed = True
    expense.recurring_rule_id = rule.id
    session.commit()
    return rule


def list_rules(session: Session, group_id: int) -> list[RecurringRule]:
    query = select(RecurringRule).where(RecurringRule.group_id == group_id)
    return list(session.scalars(query.order_by(RecurringRule.amount_cents.desc())))


def update_amount(session: Session, rule: RecurringRule, amount_cents: int) -> RecurringRule:
    """Change the amount of all future entries (e.g. after a rent increase)."""
    if amount_cents <= 0:
        raise ValidationError("The amount must be greater than 0")
    rule.amount_cents = amount_cents
    session.commit()
    return rule


def delete_rule(session: Session, rule: RecurringRule) -> None:
    """Stop the standing order; entries booked so far stay."""
    session.delete(rule)
    session.commit()


def book_due(session: Session, group_id: int, today: dt.date) -> int:
    """Enter every standing-order payment that is due by today; returns how many."""
    booked = 0
    for rule in list_rules(session, group_id):
        while rule.next_date <= today:
            session.add(
                Expense(
                    group_id=group_id,
                    payer_id=rule.payer_id,
                    amount_cents=rule.amount_cents,
                    date=rule.next_date,
                    description=rule.description,
                    category=rule.category,
                    is_fixed=True,
                    split_method=SplitMethod(rule.split_method),
                    recurring_rule_id=rule.id,
                    shares=[ExpenseShare(member_id=p["member_id"], percent=p["percent"]) for p in rule.participants],
                )
            )
            rule.next_date = add_month(rule.next_date, rule.day_of_month)
            booked += 1
    if booked:
        try:
            session.commit()
        except IntegrityError:
            # Someone else's request booked the same entries a moment earlier
            session.rollback()
            return 0
    return booked
