"""API endpoint for category suggestions (billbuddy.ml.categorizer)."""

from typing import Annotated

from fastapi import APIRouter, Query

from billbuddy.api.deps import CurrentUser, SessionDep
from billbuddy.api.schemas import SuggestionOut
from billbuddy.auth import access
from billbuddy.ml.categorizer import service

router = APIRouter(prefix="/api")


@router.get("/groups/{group_id}/suggest-category", response_model=SuggestionOut)
def suggest_category(
    group_id: int,
    user: CurrentUser,
    session: SessionDep,
    description: Annotated[str, Query(max_length=200)],
    amount: Annotated[float, Query(ge=0)] = 0,
):
    access.require_group(session, user, group_id)
    suggestion = service.suggest(session, group_id, description, amount)
    if suggestion is None:
        return SuggestionOut(category=None, confidence=None)
    return SuggestionOut(category=suggestion.category, confidence=round(suggestion.confidence, 3))
