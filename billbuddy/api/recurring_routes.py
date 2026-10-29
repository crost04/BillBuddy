"""API endpoints for fixed costs: recognized series (billbuddy.ml.recurring) and
standing orders that enter them automatically (billbuddy.expenses.recurring_rules)."""

from fastapi import APIRouter

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import (
    DismissIn,
    MarkFixedIn,
    MarkFixedOut,
    RecurringOut,
    RecurringRuleIn,
    RecurringRuleOut,
    RuleAmountIn,
    to_cents,
)
from billbuddy.auth import access
from billbuddy.clock import today
from billbuddy.expenses import recurring_rules
from billbuddy.ml.recurring import service
from billbuddy.ml.recurring.model import description_key

router = APIRouter(prefix="/api")


# --- Recognized series ---


@router.get("/groups/{group_id}/recurring", response_model=list[RecurringOut])
def list_recurring(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    recurring_rules.book_due(session, group_id, today())
    rule_keys = {description_key(r.description) for r in recurring_rules.list_rules(session, group_id)}
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
            has_rule=s.key in rule_keys,
            last_expense_id=s.expense_ids[-1],
        )
        for s in service.group_series(session, group_id)
    ]


@router.post("/groups/{group_id}/recurring/mark-fixed", response_model=MarkFixedOut)
def mark_fixed(group_id: int, body: MarkFixedIn, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return MarkFixedOut(changed=service.mark_fixed(session, group_id, body.key))


@router.post("/groups/{group_id}/recurring/dismiss", status_code=204)
def dismiss(group_id: int, body: DismissIn, user: CurrentUser, session: SessionDep):
    """'Keine Fixkosten': do not suggest this description again."""
    access.require_group(session, user, group_id)
    service.dismiss(session, group_id, body.key)


# --- Standing orders ---


@router.get("/groups/{group_id}/recurring-rules", response_model=list[RecurringRuleOut])
def list_rules(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return recurring_rules.list_rules(session, group_id)


@router.post("/groups/{group_id}/recurring-rules", response_model=RecurringRuleOut, status_code=201)
def create_rule(group_id: int, body: RecurringRuleIn, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    access.require_expense(session, user, body.expense_id)
    rule = recurring_rules.create_from_expense(session, group_id, body.expense_id)
    # Earlier payments of the same series count as fixed costs too
    service.mark_fixed(session, group_id, description_key(rule.description))
    return rule


@router.put("/recurring-rules/{rule_id}", response_model=RecurringRuleOut)
def update_rule(rule_id: int, body: RuleAmountIn, user: CurrentUser, session: SessionDep):
    rule = access.require_recurring_rule(session, user, rule_id)
    return recurring_rules.update_amount(session, rule, to_cents(body.amount))


@router.delete("/recurring-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: CurrentUser, session: SessionDep):
    rule = access.require_recurring_rule(session, user, rule_id)
    recurring_rules.delete_rule(session, rule)
