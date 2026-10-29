"""API endpoints for balances, suggested transfers and recorded payments."""

import re

from fastapi import APIRouter
from fastapi.responses import Response

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import (
    BalanceOut,
    PaymentIn,
    PaymentOut,
    SettlementOut,
    TransferOut,
    to_cents,
)
from billbuddy.auth import access
from billbuddy.clock import today
from billbuddy.expenses import recurring_rules
from billbuddy.settlement import service
from billbuddy.settlement.export import group_csv

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/settlement", response_model=SettlementOut)
def get_settlement(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    recurring_rules.book_due(session, group_id, today())
    settlement = service.get_settlement(session, group_id)
    return SettlementOut(
        balances=[
            BalanceOut(member_id=member_id, balance=cents / 100) for member_id, cents in settlement.balances.items()
        ],
        transfers=[
            TransferOut(
                from_member_id=t.from_member_id,
                to_member_id=t.to_member_id,
                amount=t.amount_cents / 100,
            )
            for t in settlement.transfers
        ],
    )


@router.get("/groups/{group_id}/payments", response_model=list[PaymentOut])
def list_payments(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return service.list_payments(session, group_id)


@router.post("/groups/{group_id}/payments", response_model=PaymentOut, status_code=201)
def create_payment(group_id: int, body: PaymentIn, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return service.create_payment(
        session, group_id, body.from_member_id, body.to_member_id, to_cents(body.amount), body.date
    )


@router.delete("/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: int, user: CurrentUser, session: SessionDep):
    access.require_payment(session, user, payment_id)
    service.delete_payment(session, payment_id)


@router.get("/groups/{group_id}/export.csv")
def export_csv(group_id: int, user: CurrentUser, session: SessionDep):
    """All expenses and payments of the group as a CSV file (backup, opens in Excel/Numbers)."""
    group = access.require_group(session, user, group_id)
    recurring_rules.book_due(session, group_id, today())
    slug = re.sub(r"[^a-z0-9]+", "-", group.name.lower()).strip("-") or "gruppe"
    filename = f"billbuddy-{slug}-{today().isoformat()}.csv"
    return Response(
        content=group_csv(group),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
