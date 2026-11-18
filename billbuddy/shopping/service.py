"""Shopping list logic: list, add, tick off and remove entries."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from billbuddy.expenses.service import ValidationError
from billbuddy.shopping.models import ShoppingItem

MAX_NAME_LENGTH = 100


def list_items(session: Session, group_id: int) -> list[ShoppingItem]:
    """Open entries first (oldest on top, like a written list), ticked-off ones below."""
    query = select(ShoppingItem).where(ShoppingItem.group_id == group_id)
    return list(session.scalars(query.order_by(ShoppingItem.checked, ShoppingItem.created_at, ShoppingItem.id)))


def add_item(session: Session, group_id: int, name: str, added_by_id: int | None) -> ShoppingItem:
    """Put something on the list. If it is already on it (and not ticked off yet),
    that entry is returned instead of a second "Milch"."""
    name = _clean(name)
    for item in list_items(session, group_id):
        if not item.checked and item.name.casefold() == name.casefold():
            return item
    item = ShoppingItem(group_id=group_id, name=name, added_by_id=added_by_id)
    session.add(item)
    session.commit()
    return item


def update_item(
    session: Session, item: ShoppingItem, name: str | None = None, checked: bool | None = None
) -> ShoppingItem:
    if name is not None:
        item.name = _clean(name)
    if checked is not None:
        item.checked = checked
    session.commit()
    return item


def delete_item(session: Session, item: ShoppingItem) -> None:
    session.delete(item)
    session.commit()


def remove_items(session: Session, group_id: int, ids: list[int]) -> int:
    """Remove several entries at once (bought according to a receipt, or the ticked-off
    ones). Ids of other groups are ignored. Returns how many were removed."""
    if not ids:
        return 0
    result = session.execute(delete(ShoppingItem).where(ShoppingItem.group_id == group_id, ShoppingItem.id.in_(ids)))
    session.commit()
    return result.rowcount


def _clean(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValidationError("Please enter what is needed")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"At most {MAX_NAME_LENGTH} characters")
    return name
