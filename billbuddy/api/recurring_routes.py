"""API endpoints for recognized fixed costs (billbuddy.ml.recurring)."""

from fastapi import APIRouter

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import MarkFixedIn, MarkFixedOut, RecurringOut
from billbuddy.auth import access
from billbuddy.ml.recurring import service

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/recurring", response_model=list[RecurringOut])
def list_recurring(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return [
        RecurringOut(
            key=s.key,
            description=s.description,
            count=s.count,
            typical_amount=s.typical_amount_cents / 100,
            day_of_month=s.day_of_month,
            last_date=s.last_date,
            next_date=s.next_date,
            active=s.active,
            already_fixed=s.already_fixed,
        )
        for s in service.group_series(session, group_id)
    ]


@router.post("/groups/{group_id}/recurring/mark-fixed", response_model=MarkFixedOut)
def mark_fixed(group_id: int, body: MarkFixedIn, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return MarkFixedOut(changed=service.mark_fixed(session, group_id, body.key))
