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


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    members: list[str] = []


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
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
