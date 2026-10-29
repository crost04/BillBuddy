"""API endpoints for registration, login, logout and invitations."""

import os

from fastapi import APIRouter, Request, Response

from billbuddy.api.deps import SESSION_COOKIE, CurrentUser, SessionDep
from billbuddy.api.schemas import (
    GroupOut,
    InviteMemberOut,
    InviteOut,
    JoinIn,
    LoginIn,
    RegisterIn,
    UserOut,
)
from billbuddy.auth import access, service
from billbuddy.auth.service import SESSION_DAYS, AuthError

router = APIRouter(prefix="/api")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,  # JavaScript cannot read it, so injected scripts cannot steal it
        samesite="lax",  # not sent with requests from other websites (protects against CSRF)
        # Only over HTTPS; switched on on the server, off for local http://
        secure=os.environ.get("BILLBUDDY_SECURE_COOKIES", "").lower() in ("1", "true", "yes"),
    )


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, response: Response, session: SessionDep):
    user = service.register(session, body.email, body.name, body.password)
    _set_session_cookie(response, service.create_session(session, user))
    return user


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, session: SessionDep):
    limiter = request.app.state.login_limiter
    limiter.check(body.email)
    try:
        user = service.authenticate(session, body.email, body.password)
    except AuthError:
        limiter.record_failure(body.email)
        raise
    limiter.reset(body.email)
    _set_session_cookie(response, service.create_session(session, user))
    return user


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: SessionDep):
    service.end_session(session, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.get("/invites/{code}", response_model=InviteOut)
def get_invite(code: str, user: CurrentUser, session: SessionDep):
    group = access.group_for_invite(session, code)
    return InviteOut(
        group_name=group.name,
        members=[InviteMemberOut(id=m.id, name=m.name, has_account=m.user_id is not None) for m in group.members],
    )


@router.post("/invites/{code}/join", response_model=GroupOut)
def join(code: str, body: JoinIn, user: CurrentUser, session: SessionDep):
    return access.join_group(session, user, code, body.member_id)
