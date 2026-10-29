"""Registration, login and logout."""

import datetime as dt
import functools
import hashlib
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from billbuddy.auth.models import AuthSession, User
from billbuddy.auth.passwords import hash_password, verify_password
from billbuddy.expenses.service import ValidationError

SESSION_DAYS = 90  # stay logged in on the phone for three months
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Login failed, or the request has no valid session."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(session: Session, email: str, name: str, password: str) -> User:
    email = normalize_email(email)
    name = name.strip()
    if "@" not in email or len(email) > 254:
        raise ValidationError("Please enter a valid email address")
    if not name:
        raise ValidationError("The name must not be empty")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"The password needs at least {MIN_PASSWORD_LENGTH} characters")
    if session.scalar(select(User).where(User.email == email)):
        raise ValidationError("There is already an account with this email address")

    user = User(email=email, name=name, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    # Check a dummy hash for unknown emails, so the answer takes equally long and
    # nobody can find out which addresses have an account
    stored_hash = user.password_hash if user else _dummy_hash()
    if not verify_password(password, stored_hash) or user is None:
        raise AuthError("Wrong email or password")
    return user


def create_session(session: Session, user: User) -> str:
    """Log the user in on one device and return the token for the cookie."""
    token = secrets.token_urlsafe(32)
    expires_at = dt.datetime.now() + dt.timedelta(days=SESSION_DAYS)
    session.add(AuthSession(user=user, token_hash=_hash_token(token), expires_at=expires_at))
    session.commit()
    return token


def user_for_token(session: Session, token: str | None) -> User:
    if not token:
        raise AuthError("Not logged in")
    # joinedload: session and user in one query (this runs for every request)
    query = (
        select(AuthSession).options(joinedload(AuthSession.user)).where(AuthSession.token_hash == _hash_token(token))
    )
    auth_session = session.scalar(query)
    if auth_session is None or auth_session.expires_at < dt.datetime.now():
        raise AuthError("Not logged in")
    return auth_session.user


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
        session.commit()


def _hash_token(token: str) -> str:
    # Tokens are long random strings, so a plain SHA-256 (without salt) is enough here
    return hashlib.sha256(token.encode()).hexdigest()


@functools.cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))
