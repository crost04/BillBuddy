"""API endpoints for the shared shopping list (billbuddy.shopping)."""

from fastapi import APIRouter

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import RemovedOut, RemoveShoppingItemsIn, ShoppingItemIn, ShoppingItemOut, ShoppingItemUpdate
from billbuddy.auth import access
from billbuddy.shopping import service

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/shopping-items", response_model=list[ShoppingItemOut])
def list_items(group_id: int, user: CurrentUser, session: SessionDep):
    access.require_group(session, user, group_id)
    return service.list_items(session, group_id)


@router.post("/groups/{group_id}/shopping-items", response_model=ShoppingItemOut, status_code=201)
def add_item(group_id: int, body: ShoppingItemIn, user: CurrentUser, session: SessionDep):
    group = access.require_group(session, user, group_id)
    me = next(m for m in group.members if m.user_id == user.id)
    return service.add_item(session, group_id, body.name, added_by_id=me.id)


@router.put("/shopping-items/{item_id}", response_model=ShoppingItemOut)
def update_item(item_id: int, body: ShoppingItemUpdate, user: CurrentUser, session: SessionDep):
    item = access.require_shopping_item(session, user, item_id)
    return service.update_item(session, item, name=body.name, checked=body.checked)


@router.delete("/shopping-items/{item_id}", status_code=204)
def delete_item(item_id: int, user: CurrentUser, session: SessionDep):
    item = access.require_shopping_item(session, user, item_id)
    service.delete_item(session, item)


@router.post("/groups/{group_id}/shopping-items/remove", response_model=RemovedOut)
def remove_items(group_id: int, body: RemoveShoppingItemsIn, user: CurrentUser, session: SessionDep):
    """Remove several entries: the ones bought according to a receipt, or all ticked-off ones."""
    access.require_group(session, user, group_id)
    return RemovedOut(removed=service.remove_items(session, group_id, body.ids))
