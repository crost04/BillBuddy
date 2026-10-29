"""Database models for user accounts and login sessions."""

import datetime as dt

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billbuddy.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Always stored in lower case, so "Anna@Mail.de" and "anna@mail.de" are the same account
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    # Never the password itself, only a salted hash (see passwords.py)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)


class AuthSession(Base):
    """One logged-in device.

    The browser keeps a random token in a cookie. Only a hash of the token is
    stored here, so someone who reads the database still cannot log in.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)
    expires_at: Mapped[dt.datetime]

    user: Mapped[User] = relationship()
