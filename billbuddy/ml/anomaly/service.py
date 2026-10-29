"""Anomaly checks for a group: before saving an expense and for the overview."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.expenses.models import Expense
from billbuddy.ml.anomaly.model import Entry, OutlierCheck, OutlierModel, duplicates_of, find_duplicates


def group_entries(session: Session, group_id: int) -> list[Entry]:
    query = select(Expense.id, Expense.date, Expense.description, Expense.amount_cents, Expense.category).where(
        Expense.group_id == group_id
    )
    return [Entry(*row) for row in session.execute(query)]


def check(session: Session, group_id: int, candidate: Entry) -> tuple[list[Entry], OutlierCheck]:
    """Possible duplicates of a new or edited expense, and whether its amount is unusual."""
    others = [e for e in group_entries(session, group_id) if e.expense_id != candidate.expense_id]
    return duplicates_of(candidate, others), OutlierModel(others).check(candidate.category, candidate.amount_cents)


def month_anomalies(session: Session, group_id: int, month: str) -> list[dict]:
    """Duplicates and unusually high amounts among the expenses of one month ("YYYY-MM")."""
    entries = group_entries(session, group_id)
    in_month = [e for e in entries if e.date.strftime("%Y-%m") == month]
    result = []
    for first, second in find_duplicates(entries):
        if second in in_month:
            result.append({"kind": "duplicate", "entry": second, "other": first})
    model = OutlierModel(entries)
    for entry in in_month:
        outlier = model.check(entry.category, entry.amount_cents)
        if outlier.is_outlier:
            result.append({"kind": "outlier", "entry": entry, "check": outlier})
    return sorted(result, key=lambda a: a["entry"].date, reverse=True)
