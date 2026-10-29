"""Access control: who may see which group.

A user may access a group if one of its members is linked to the user's
account. New people join through the group's invitation link.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.auth.models import User
from billbuddy.expenses.models import Expense, Group, Member, Payment
from billbuddy.expenses.service import NotFoundError, ValidationError


def user_groups(session: Session, user: User) -> list[Group]:
    query = select(Group).join(Member).where(Member.user_id == user.id).order_by(Group.name)
    return list(session.scalars(query))


def require_group(session: Session, user: User, group_id: int) -> Group:
    group = session.get(Group, group_id)
    if group is None or not any(m.user_id == user.id for m in group.members):
        # "Not found" instead of "forbidden": strangers should not even learn that it exists
        raise NotFoundError(f"Group {group_id} not found")
    return group


def require_member(session: Session, user: User, member_id: int) -> Member:
    return _require_in_group(session, user, Member, member_id)


def require_expense(session: Session, user: User, expense_id: int) -> Expense:
    return _require_in_group(session, user, Expense, expense_id)


def require_payment(session: Session, user: User, payment_id: int) -> Payment:
    return _require_in_group(session, user, Payment, payment_id)


def _require_in_group(session: Session, user: User, model, object_id: int):
    obj = session.get(model, object_id)
    if obj is None:
        raise NotFoundError(f"{model.__name__} {object_id} not found")
    try:
        require_group(session, user, obj.group_id)
    except NotFoundError:
        raise NotFoundError(f"{model.__name__} {object_id} not found") from None
    return obj


# --- Invitations ---


def group_for_invite(session: Session, code: str) -> Group:
    group = session.scalar(select(Group).where(Group.invite_code == code))
    if group is None:
        raise NotFoundError("This invitation link is not valid")
    return group


def join_group(session: Session, user: User, code: str, member_id: int | None) -> Group:
    """Link the user to a group.

    member_id: an existing person in the group without an account (e.g. someone
    who was added by name before), or None to join as a new person.
    """
    group = group_for_invite(session, code)
    if any(m.user_id == user.id for m in group.members):
        return group

    if member_id is None:
        group.members.append(Member(name=_unique_name(group, user.name), user_id=user.id))
    else:
        member = next((m for m in group.members if m.id == member_id), None)
        if member is None:
            raise ValidationError("This person is not part of the group")
        if member.user_id is not None:
            raise ValidationError("This person is already linked to another account")
        member.user_id = user.id
    session.commit()
    return group


def _unique_name(group: Group, name: str) -> str:
    taken = {m.name for m in group.members}
    candidate, number = name, 2
    while candidate in taken:
        candidate, number = f"{name} {number}", number + 1
    return candidate
