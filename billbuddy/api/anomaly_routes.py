"""API endpoints for duplicates and unusually high amounts (billbuddy.ml.anomaly)."""

from typing import Annotated

from fastapi import APIRouter, Query

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import (
    AnomalyOut,
    CheckExpenseIn,
    CheckExpenseOut,
    OutlierOut,
    SimilarExpenseOut,
    to_cents,
)
from billbuddy.auth import access
from billbuddy.clock import today
from billbuddy.ml.anomaly import service
from billbuddy.ml.anomaly.model import Entry

router = APIRouter(prefix="/api")


@router.post("/groups/{group_id}/check-expense", response_model=CheckExpenseOut)
def check_expense(group_id: int, body: CheckExpenseIn, user: CurrentUser, session: SessionDep):
    """Called by the form before saving: does this look like a duplicate or a typo?"""
    access.require_group(session, user, group_id)
    candidate = Entry(body.expense_id, body.date, body.description, to_cents(body.amount), body.category)
    duplicates, outlier = service.check(session, group_id, candidate)
    return CheckExpenseOut(
        duplicates=[_similar(e) for e in duplicates],
        outlier=OutlierOut(
            is_outlier=outlier.is_outlier,
            typical=None if outlier.typical_cents is None else outlier.typical_cents / 100,
            ratio=outlier.ratio,
        ),
    )


@router.get("/groups/{group_id}/anomalies", response_model=list[AnomalyOut])
def list_anomalies(
    group_id: int,
    user: CurrentUser,
    session: SessionDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-10")] = None,
):
    access.require_group(session, user, group_id)
    result = []
    for anomaly in service.month_anomalies(session, group_id, month or today().strftime("%Y-%m")):
        entry = anomaly["entry"]
        out = AnomalyOut(kind=anomaly["kind"], expense=_similar(entry), category=entry.category)
        if anomaly["kind"] == "duplicate":
            out.other = _similar(anomaly["other"])
        else:
            out.typical = anomaly["check"].typical_cents / 100
            out.ratio = anomaly["check"].ratio
        result.append(out)
    return result


def _similar(entry: Entry) -> SimilarExpenseOut:
    return SimilarExpenseOut(
        id=entry.expense_id, description=entry.description, amount=entry.amount_cents / 100, date=entry.date
    )
