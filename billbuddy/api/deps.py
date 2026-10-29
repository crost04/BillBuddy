"""Dependencies shared by all API routes."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from billbuddy.auth import service as auth_service
from billbuddy.auth.models import User

# Name of the cookie that keeps the login on this device
SESSION_COOKIE = "billbuddy_session"


def get_session(request: Request):
    """One database session per request, closed automatically afterwards."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(request: Request, session: SessionDep) -> User:
    """The logged-in user; raises AuthError (-> 401) without a valid session cookie."""
    return auth_service.user_for_token(session, request.cookies.get(SESSION_COOKIE))


CurrentUser = Annotated[User, Depends(get_current_user)]
