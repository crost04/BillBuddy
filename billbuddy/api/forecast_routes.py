"""API endpoint for the overview screen: spending per category, person and month, with forecast."""

from typing import Annotated

from fastapi import APIRouter, Query

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import ForecastOut, MemberPaidOut, MonthTotalOut, OverviewOut
from billbuddy.auth import access
from billbuddy.expenses import recurring_rules
from billbuddy.ml.forecast import service
from billbuddy.ml.forecast.model import Forecast, forecast_month, spent_until

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/overview", response_model=OverviewOut)
def overview(
    group_id: int,
    user: CurrentUser,
    session: SessionDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-10")] = None,
):
    group = access.require_group(session, user, group_id)
    recurring_rules.book_due(session, group_id, service.today())
    records = service.group_records(session, group_id)
    result = forecast_month(records, service.today(), month)

    paid = {m.id: 0 for m in group.members}
    for expense in group.expenses:
        if expense.date.strftime("%Y-%m") == result.month:
            paid[expense.payer_id] += expense.amount_cents

    return OverviewOut(
        month=result.month,
        is_current=result.is_current,
        day=result.day,
        days_in_month=result.days_in_month,
        history_months=len(result.history_months),
        total=_forecast_out(result.total),
        categories=[_forecast_out(f) for f in result.categories],
        members=[MemberPaidOut(member_id=member_id, paid=cents / 100) for member_id, cents in paid.items()],
        history=[
            MonthTotalOut(month=m, total=spent_until(records, m, 31) / 100)
            for m in [*result.history_months, result.month]
        ],
    )


def _forecast_out(f: Forecast) -> ForecastOut:
    def euros(cents):
        return None if cents is None else cents / 100

    return ForecastOut(
        category=f.category,
        spent=f.spent_cents / 100,
        forecast=euros(f.forecast_cents),
        low=euros(f.low_cents),
        high=euros(f.high_cents),
        average=euros(f.average_cents),
    )
