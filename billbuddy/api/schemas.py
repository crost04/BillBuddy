"""Request and response formats of the API (validated by Pydantic).

Amounts are sent as euros with up to two decimals (e.g. 34.5) and converted
to cents for the database.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from billbuddy.expenses.models import SplitMethod


def to_cents(amount: Decimal | None) -> int | None:
    return None if amount is None else int(amount * 100)


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    monthly_income: Decimal | None = Field(default=None, ge=0, decimal_places=2, max_digits=10)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    monthly_income: float | None
    # The linked account, if this person uses the app
    user_id: int | None


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # The other people; the logged-in user is added automatically as the first member
    members: list[str] = []


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    invite_code: str
    members: list[MemberOut]


class ParticipantIn(BaseModel):
    member_id: int
    # Only needed for split_method "percent"
    percent: float | None = None


class ExpenseIn(BaseModel):
    payer_id: int
    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    date: dt.date
    description: str = Field(min_length=1, max_length=200)
    category: str | None = None
    is_fixed: bool = False
    split_method: SplitMethod = SplitMethod.EQUAL
    participants: list[ParticipantIn] = Field(min_length=1)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: int
    percent: float | None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    payer_id: int
    amount: float
    date: dt.date
    description: str
    category: str | None
    is_fixed: bool
    split_method: SplitMethod
    shares: list[ShareOut]
    created_at: dt.datetime


class BalanceOut(BaseModel):
    member_id: int
    # Positive: gets money back. Negative: owes money.
    balance: float


class TransferOut(BaseModel):
    from_member_id: int
    to_member_id: int
    amount: float


class SettlementOut(BaseModel):
    balances: list[BalanceOut]
    transfers: list[TransferOut]


class PaymentIn(BaseModel):
    from_member_id: int
    to_member_id: int
    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    date: dt.date


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    from_member_id: int
    to_member_id: int
    amount: float
    date: dt.date
    created_at: dt.datetime


# --- Accounts and invitations ---


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(max_length=100)
    password: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str


class InviteMemberOut(BaseModel):
    id: int
    name: str
    has_account: bool


class InviteOut(BaseModel):
    group_name: str
    members: list[InviteMemberOut]


class JoinIn(BaseModel):
    # An existing person without an account, or None to join as a new person
    member_id: int | None = None
