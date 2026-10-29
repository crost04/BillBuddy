"""API endpoints for balances, suggested transfers and recorded payments."""

from fastapi import APIRouter

from billbuddy.api.deps import SessionDep
from billbuddy.api.schemas import (
    BalanceOut,
    PaymentIn,
    PaymentOut,
    SettlementOut,
    TransferOut,
    to_cents,
)
from billbuddy.settlement import service

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/settlement", response_model=SettlementOut)
def get_settlement(group_id: int, session: SessionDep):
    settlement = service.get_settlement(session, group_id)
    return SettlementOut(
        balances=[
            BalanceOut(member_id=member_id, balance=cents / 100)
            for member_id, cents in settlement.balances.items()
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
def list_payments(group_id: int, session: SessionDep):
    return service.list_payments(session, group_id)


@router.post("/groups/{group_id}/payments", response_model=PaymentOut, status_code=201)
def create_payment(group_id: int, body: PaymentIn, session: SessionDep):
    return service.create_payment(
        session, group_id, body.from_member_id, body.to_member_id, to_cents(body.amount), body.date
    )


@router.delete("/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: int, session: SessionDep):
    service.delete_payment(session, payment_id)
