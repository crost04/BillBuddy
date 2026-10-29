"""API endpoint for the receipt scan (billbuddy.ml.receipt_ocr)."""

from fastapi import APIRouter

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import ReceiptItemOut, ReceiptOut, ReceiptTextIn
from billbuddy.auth import access
from billbuddy.clock import today
from billbuddy.ml.categorizer import service as categorizer
from billbuddy.ml.receipt_ocr.parser import parse_receipt

router = APIRouter(prefix="/api")


@router.post("/groups/{group_id}/parse-receipt", response_model=ReceiptOut)
def parse(group_id: int, body: ReceiptTextIn, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    receipt = parse_receipt(body.text, today())
    total = receipt.total_cents if receipt.total_cents is not None else receipt.items_sum_cents or None
    suggestion = categorizer.suggest(session, group_id, receipt.store, (total or 0) / 100) if receipt.store else None
    return ReceiptOut(
        store=receipt.store,
        date=receipt.date,
        total=None if total is None else total / 100,
        items=[ReceiptItemOut(name=i.name, amount=i.amount_cents / 100) for i in receipt.items],
        items_sum=receipt.items_sum_cents / 100,
        items_match_total=receipt.items_match_total,
        category=suggestion.category if suggestion else None,
        confidence=round(suggestion.confidence, 3) if suggestion else None,
    )
