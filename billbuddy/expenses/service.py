"""Business logic for groups, members and expenses.

The API calls these functions instead of working with the models directly.
They check that the input makes sense before anything is saved, so invalid
data never reaches the database (data quality).
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from billbuddy.expenses.categories import CATEGORIES
from billbuddy.expenses.models import Expense, ExpenseShare, Group, Member, SplitMethod


class NotFoundError(LookupError):
    """The requested object does not exist."""


class ValidationError(ValueError):
    """The input breaks a rule, e.g. percentages that do not add up to 100."""


@dataclass
class ExpenseInput:
    payer_id: int
    amount_cents: int
    date: dt.date
    description: str
    # Members who share the cost; can be a subset of the group
    participant_ids: list[int]
    category: str | None = None
    is_fixed: bool = False
    split_method: SplitMethod = SplitMethod.EQUAL
    # Only for SplitMethod.PERCENT: {member_id: percent}
    percents: dict[int, float] | None = None
    # The categorizer's suggestion shown while entering the expense (kept for evaluation)
    suggested_category: str | None = None


# --- Groups and members ---


def create_group(
    session: Session, name: str, member_names: list[str] = (), creator_user_id: int | None = None
) -> Group:
    """Create a group; creator_user_id links the first member to the creator's account."""
    if len(set(member_names)) != len(member_names):
        raise ValidationError("Member names must be unique within a group")
    group = Group(name=name, members=[Member(name=n) for n in member_names])
    if creator_user_id is not None and group.members:
        group.members[0].user_id = creator_user_id
    session.add(group)
    session.commit()
    return group


def list_groups(session: Session) -> list[Group]:
    return list(session.scalars(select(Group).order_by(Group.name)))


def get_group(session: Session, group_id: int) -> Group:
    return _get(session, Group, group_id)


def delete_group(session: Session, group_id: int) -> None:
    session.delete(get_group(session, group_id))
    session.commit()


def add_member(
    session: Session, group_id: int, name: str, monthly_income_cents: int | None = None
) -> Member:
    group = get_group(session, group_id)
    if any(m.name == name for m in group.members):
        raise ValidationError(f"There is already a member called {name!r}")
    member = Member(name=name, monthly_income_cents=monthly_income_cents)
    group.members.append(member)
    session.commit()
    return member


def update_member(
    session: Session, member_id: int, name: str, monthly_income_cents: int | None
) -> Member:
    member = _get(session, Member, member_id)
    if any(m.name == name and m.id != member_id for m in member.group.members):
        raise ValidationError(f"There is already a member called {name!r}")
    member.name = name
    member.monthly_income_cents = monthly_income_cents
    session.commit()
    return member


# --- Expenses ---


def create_expense(session: Session, group_id: int, data: ExpenseInput) -> Expense:
    group = get_group(session, group_id)
    expense = Expense()
    _apply(expense, group, data)
    if data.suggested_category is not None and data.suggested_category not in CATEGORIES:
        raise ValidationError(f"Unknown category {data.suggested_category!r}")
    # Only stored once, when the expense is entered; later edits keep the original suggestion
    expense.suggested_category = data.suggested_category
    # Attach to the group only after validation, so a rejected expense is never saved
    expense.group = group
    session.add(expense)
    session.commit()
    return expense


def update_expense(session: Session, expense_id: int, data: ExpenseInput) -> Expense:
    expense = get_expense(session, expense_id)
    _apply(expense, expense.group, data)
    session.commit()
    return expense


def get_expense(session: Session, expense_id: int) -> Expense:
    return _get(session, Expense, expense_id)


def delete_expense(session: Session, expense_id: int) -> None:
    session.delete(get_expense(session, expense_id))
    session.commit()


def list_expenses(
    session: Session, group_id: int, start: dt.date | None = None, end: dt.date | None = None
) -> list[Expense]:
    """Expenses of a group, newest first, optionally limited to start..end (inclusive)."""
    get_group(session, group_id)
    # selectinload: fetch the shares of all expenses in one extra query instead of one per expense
    query = select(Expense).options(selectinload(Expense.shares)).where(Expense.group_id == group_id)
    if start:
        query = query.where(Expense.date >= start)
    if end:
        query = query.where(Expense.date <= end)
    return list(session.scalars(query.order_by(Expense.date.desc(), Expense.id.desc())))


# --- Helpers ---


def _get(session: Session, model, object_id: int):
    obj = session.get(model, object_id)
    if obj is None:
        raise NotFoundError(f"{model.__name__} {object_id} not found")
    return obj


def _apply(expense: Expense, group: Group, data: ExpenseInput) -> None:
    """Validate the input and copy it onto the expense (including its shares)."""
    if data.amount_cents <= 0:
        raise ValidationError("The amount must be greater than 0")
    if not data.description.strip():
        raise ValidationError("The description must not be empty")
    if data.category is not None and data.category not in CATEGORIES:
        raise ValidationError(f"Unknown category {data.category!r}")

    members = {m.id: m for m in group.members}
    if data.payer_id not in members:
        raise ValidationError("The payer must be a member of the group")
    if not data.participant_ids:
        raise ValidationError("At least one member must take part in the expense")
    if len(set(data.participant_ids)) != len(data.participant_ids):
        raise ValidationError("A member can take part only once")
    if any(pid not in members for pid in data.participant_ids):
        raise ValidationError("All participants must be members of the group")

    participants = [members[pid] for pid in data.participant_ids]
    percents = _percents(data, participants)

    expense.payer = members[data.payer_id]
    expense.amount_cents = data.amount_cents
    expense.date = data.date
    expense.description = data.description.strip()
    expense.category = data.category
    expense.is_fixed = data.is_fixed
    expense.split_method = data.split_method

    # Reuse existing share rows when editing; deleting and re-inserting the
    # same member would clash with the one-share-per-member constraint
    existing = {s.member_id: s for s in expense.shares}
    shares = []
    for member in participants:
        share = existing.get(member.id) or ExpenseShare(member=member)
        share.percent = percents.get(member.id)
        shares.append(share)
    expense.shares = shares


def _percents(data: ExpenseInput, participants: list[Member]) -> dict[int, float]:
    """Each participant's percentage; empty for an equal split."""
    if data.split_method == SplitMethod.EQUAL:
        return {}

    if data.split_method == SplitMethod.PERCENT:
        percents = data.percents or {}
        if set(percents) != {m.id for m in participants}:
            raise ValidationError("Give a percentage for every participant")
        if any(p <= 0 for p in percents.values()):
            raise ValidationError("Percentages must be greater than 0")
        if abs(sum(percents.values()) - 100) > 0.01:
            raise ValidationError("Percentages must add up to 100")
        return percents

    # SplitMethod.INCOME: snapshot of the current incomes
    if any(not m.monthly_income_cents for m in participants):
        raise ValidationError("Every participant needs a monthly income to split by income")
    total = sum(m.monthly_income_cents for m in participants)
    return {m.id: m.monthly_income_cents / total * 100 for m in participants}
