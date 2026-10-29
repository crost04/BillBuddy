"""Tests for the auth module: passwords, accounts, sessions and access control."""

import datetime as dt

import pytest

from billbuddy.auth import access, service
from billbuddy.auth.models import AuthSession
from billbuddy.auth.passwords import hash_password, verify_password
from billbuddy.auth.service import AuthError
from billbuddy.expenses import service as expenses
from billbuddy.expenses.service import NotFoundError, ValidationError

PASSWORD = "correct horse"


@pytest.fixture
def anna(session):
    return service.register(session, "Anna@Example.com", "Anna", PASSWORD)


@pytest.fixture
def ben(session):
    return service.register(session, "ben@example.com", "Ben", PASSWORD)


# --- Passwords ---


def test_password_hash_can_be_verified():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong password", stored)


def test_same_password_gives_different_hashes():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_broken_hash_is_rejected():
    assert not verify_password(PASSWORD, "not-a-hash")


# --- Registration and login ---


def test_register_stores_lowercase_email(anna):
    assert anna.email == "anna@example.com"
    assert anna.password_hash != PASSWORD


@pytest.mark.parametrize(
    "email, name, password",
    [
        ("no-at-sign", "Anna", PASSWORD),
        ("anna@example.com", "  ", PASSWORD),
        ("anna@example.com", "Anna", "short"),
    ],
)
def test_invalid_registration(session, email, name, password):
    with pytest.raises(ValidationError):
        service.register(session, email, name, password)


def test_email_can_only_be_registered_once(session, anna):
    with pytest.raises(ValidationError):
        service.register(session, "ANNA@example.com", "Other Anna", PASSWORD)


def test_login(session, anna):
    assert service.authenticate(session, " anna@EXAMPLE.com ", PASSWORD) == anna


@pytest.mark.parametrize("email, password", [("anna@example.com", "wrong"), ("nobody@example.com", PASSWORD)])
def test_failed_login_gives_the_same_error(session, anna, email, password):
    with pytest.raises(AuthError, match="Wrong email or password"):
        service.authenticate(session, email, password)


# --- Sessions ---


def test_session_token_identifies_the_user(session, anna):
    token = service.create_session(session, anna)
    assert service.user_for_token(session, token) == anna


def test_only_the_token_hash_is_stored(session, anna):
    token = service.create_session(session, anna)
    stored = session.query(AuthSession).one()
    assert stored.token_hash != token


@pytest.mark.parametrize("token", [None, "", "made-up-token"])
def test_invalid_token_is_rejected(session, anna, token):
    with pytest.raises(AuthError):
        service.user_for_token(session, token)


def test_expired_session_is_rejected(session, anna):
    token = service.create_session(session, anna)
    session.query(AuthSession).one().expires_at = dt.datetime.now() - dt.timedelta(seconds=1)
    session.commit()
    with pytest.raises(AuthError):
        service.user_for_token(session, token)


def test_logout_ends_the_session(session, anna):
    token = service.create_session(session, anna)
    service.end_session(session, token)
    with pytest.raises(AuthError):
        service.user_for_token(session, token)


# --- Access control ---


def test_creator_can_access_the_group(session, anna, ben):
    group = expenses.create_group(session, "Home", ["Anna", "Ben"], creator_user_id=anna.id)
    assert access.user_groups(session, anna) == [group]
    assert access.require_group(session, anna, group.id) == group


def test_others_cannot_see_the_group(session, anna, ben):
    group = expenses.create_group(session, "Home", ["Anna", "Ben"], creator_user_id=anna.id)
    expense = expenses.create_expense(
        session,
        group.id,
        expenses.ExpenseInput(
            payer_id=group.members[0].id,
            amount_cents=1000,
            date=dt.date(2026, 10, 29),
            description="Rewe",
            participant_ids=[m.id for m in group.members],
        ),
    )

    assert access.user_groups(session, ben) == []
    with pytest.raises(NotFoundError):
        access.require_group(session, ben, group.id)
    with pytest.raises(NotFoundError):
        access.require_expense(session, ben, expense.id)
    with pytest.raises(NotFoundError):
        access.require_member(session, ben, group.members[0].id)


def test_join_as_existing_person(session, anna, ben):
    group = expenses.create_group(session, "Home", ["Anna", "Ben"], creator_user_id=anna.id)
    ben_member = group.members[1]

    access.join_group(session, ben, group.invite_code, ben_member.id)

    assert ben_member.user_id == ben.id
    assert access.user_groups(session, ben) == [group]


def test_join_as_new_person_gets_a_unique_name(session, anna):
    group = expenses.create_group(session, "Trip", ["Anna", "Ben"], creator_user_id=anna.id)
    other_ben = service.register(session, "ben2@example.com", "Ben", PASSWORD)

    access.join_group(session, other_ben, group.invite_code, None)

    assert [m.name for m in group.members] == ["Anna", "Ben", "Ben 2"]


def test_cannot_take_over_a_linked_person(session, anna, ben):
    group = expenses.create_group(session, "Home", ["Anna", "Ben"], creator_user_id=anna.id)
    with pytest.raises(ValidationError):
        access.join_group(session, ben, group.invite_code, group.members[0].id)


def test_invalid_invite_code(session, ben):
    with pytest.raises(NotFoundError):
        access.join_group(session, ben, "wrong-code", None)


def test_joining_twice_changes_nothing(session, anna):
    group = expenses.create_group(session, "Home", ["Anna", "Ben"], creator_user_id=anna.id)
    access.join_group(session, anna, group.invite_code, None)
    assert len(group.members) == 2
