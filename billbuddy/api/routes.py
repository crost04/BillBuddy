"""API endpoints. They only translate between HTTP and the service functions."""

import calendar
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from billbuddy.api.schemas import (
    ExpenseIn,
    ExpenseOut,
    GroupIn,
    GroupOut,
    MemberIn,
    MemberOut,
    to_cents,
)
from billbuddy.expenses import service
from billbuddy.expenses.categories import CATEGORIES
from billbuddy.expenses.models import SplitMethod

router = APIRouter(prefix="/api")


def get_session(request: Request):
    """One database session per request, closed automatically afterwards."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/categories")
def list_categories() -> list[str]:
    return list(CATEGORIES)


# --- Groups and members ---


@router.get("/groups", response_model=list[GroupOut])
def list_groups(session: SessionDep):
    return service.list_groups(session)


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupIn, session: SessionDep):
    return service.create_group(session, body.name, body.members)


@router.get("/groups/{group_id}", response_model=GroupOut)
def get_group(group_id: int, session: SessionDep):
    return service.get_group(session, group_id)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: int, session: SessionDep):
    service.delete_group(session, group_id)


@router.post("/groups/{group_id}/members", response_model=MemberOut, status_code=201)
def add_member(group_id: int, body: MemberIn, session: SessionDep):
    return service.add_member(session, group_id, body.name, to_cents(body.monthly_income))


@router.put("/members/{member_id}", response_model=MemberOut)
def update_member(member_id: int, body: MemberIn, session: SessionDep):
    return service.update_member(session, member_id, body.name, to_cents(body.monthly_income))


# --- Expenses ---


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseOut])
def list_expenses(
    group_id: int,
    session: SessionDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-10")] = None,
):
    start = end = None
    if month:
        year, month_number = map(int, month.split("-"))
        start = dt.date(year, month_number, 1)
        end = dt.date(year, month_number, calendar.monthrange(year, month_number)[1])
    return service.list_expenses(session, group_id, start, end)


@router.post("/groups/{group_id}/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(group_id: int, body: ExpenseIn, session: SessionDep):
    return service.create_expense(session, group_id, _to_input(body))


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, session: SessionDep):
    return service.get_expense(session, expense_id)


@router.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, body: ExpenseIn, session: SessionDep):
    return service.update_expense(session, expense_id, _to_input(body))


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, session: SessionDep):
    service.delete_expense(session, expense_id)


def _to_input(body: ExpenseIn) -> service.ExpenseInput:
    percents = None
    if body.split_method == SplitMethod.PERCENT:
        percents = {p.member_id: p.percent for p in body.participants if p.percent is not None}
    return service.ExpenseInput(
        payer_id=body.payer_id,
        amount_cents=to_cents(body.amount),
        date=body.date,
        description=body.description,
        participant_ids=[p.member_id for p in body.participants],
        category=body.category,
        is_fixed=body.is_fixed,
        split_method=body.split_method,
        percents=percents,
    )
