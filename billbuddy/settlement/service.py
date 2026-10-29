"""Balances, suggested transfers and recorded payments of a group."""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.expenses.models import Payment
from billbuddy.expenses.service import NotFoundError, ValidationError, get_group
from billbuddy.settlement.calculator import Transfer, compute_balances, minimal_transfers


@dataclass
class Settlement:
    # {member_id: cents}; positive = gets money back, negative = owes money
    balances: dict[int, int]
    # Suggested transfers to settle all debts
    transfers: list[Transfer]


def get_settlement(session: Session, group_id: int) -> Settlement:
    group = get_group(session, group_id)
    balances = compute_balances([m.id for m in group.members], group.expenses, group.payments)
    return Settlement(balances, minimal_transfers(balances))


def create_payment(
    session: Session,
    group_id: int,
    from_member_id: int,
    to_member_id: int,
    amount_cents: int,
    date: dt.date,
) -> Payment:
    group = get_group(session, group_id)
    member_ids = {m.id for m in group.members}
    if from_member_id not in member_ids or to_member_id not in member_ids:
        raise ValidationError("Both members must belong to the group")
    if from_member_id == to_member_id:
        raise ValidationError("A member cannot pay themselves")
    if amount_cents <= 0:
        raise ValidationError("The amount must be greater than 0")

    payment = Payment(
        group=group,
        from_member_id=from_member_id,
        to_member_id=to_member_id,
        amount_cents=amount_cents,
        date=date,
    )
    session.add(payment)
    session.commit()
    return payment


def list_payments(session: Session, group_id: int) -> list[Payment]:
    """Payments of a group, newest first."""
    get_group(session, group_id)
    query = (
        select(Payment)
        .where(Payment.group_id == group_id)
        .order_by(Payment.date.desc(), Payment.id.desc())
    )
    return list(session.scalars(query))


def delete_payment(session: Session, payment_id: int) -> None:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError(f"Payment {payment_id} not found")
    session.delete(payment)
    session.commit()
