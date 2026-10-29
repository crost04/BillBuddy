"""Database models for groups, members and expenses.

Money is stored as an integer number of cents (34.50 € -> 3450). Floats cannot
represent most decimal amounts exactly (0.1 + 0.2 != 0.3), and rounding errors
would add up when expenses are summed and split.
"""

import datetime as dt
import enum
import secrets
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from billbuddy.db import Base


class SplitMethod(str, enum.Enum):
    EQUAL = "equal"  # everyone involved pays the same
    PERCENT = "percent"  # custom percentage per member
    INCOME = "income"  # proportional to the members' monthly income


def new_invite_code() -> str:
    """A random, hard-to-guess code for invitation links."""
    return secrets.token_urlsafe(12)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # Whoever knows this code can join the group (see the invitation link)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, default=new_invite_code)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)

    members: Mapped[list["Member"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    recurring_rules: Mapped[list["RecurringRule"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    # Only needed for the "split by income" method
    monthly_income_cents: Mapped[int | None]
    # The account of this person, if they use the app themselves. Members without
    # an account are possible, e.g. a friend who never logs in.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    group: Mapped[Group] = relationship(back_populates="members")

    @property
    def monthly_income(self) -> Decimal | None:
        if self.monthly_income_cents is None:
            return None
        return Decimal(self.monthly_income_cents) / 100


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        # A standing order books each date only once, even if two requests arrive at the same time
        UniqueConstraint("recurring_rule_id", "date", name="one_booking_per_rule_and_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    # RESTRICT: a member who paid for something cannot simply be deleted
    payer_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    amount_cents: Mapped[int]
    date: Mapped[dt.date]
    description: Mapped[str] = mapped_column(String(200))
    # Empty until the user or the categorizer sets it
    category: Mapped[str | None] = mapped_column(String(50))
    # What the categorizer suggested when the expense was entered; comparing it with
    # `category` shows how often suggestions are kept (evaluation on real data)
    suggested_category: Mapped[str | None] = mapped_column(String(50))
    is_fixed: Mapped[bool] = mapped_column(default=False)
    split_method: Mapped[SplitMethod] = mapped_column(default=SplitMethod.EQUAL)
    # Set for expenses booked automatically by a standing order (or the one it was created from)
    recurring_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_rules.id", ondelete="SET NULL", name="fk_expenses_recurring_rule")
    )
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)

    group: Mapped[Group] = relationship(back_populates="expenses")
    payer: Mapped[Member] = relationship()
    shares: Mapped[list["ExpenseShare"]] = relationship(back_populates="expense", cascade="all, delete-orphan")

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_cents) / 100


class ExpenseShare(Base):
    """A member who takes part in an expense.

    Only the members listed here share the cost, so an expense can belong to a
    subset of the group. `percent` is empty for EQUAL. For PERCENT and INCOME it
    holds each member's percentage; for INCOME it is a snapshot taken when the
    expense is created, so a later change in income does not rewrite old expenses.
    """

    __tablename__ = "expense_shares"
    __table_args__ = (
        UniqueConstraint("expense_id", "member_id", name="one_share_per_member"),
        CheckConstraint("percent IS NULL OR (percent > 0 AND percent <= 100)", name="percent_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    percent: Mapped[float | None]

    expense: Mapped[Expense] = relationship(back_populates="shares")
    member: Mapped[Member] = relationship()


class Payment(Base):
    """Money one member transfers to another to settle debts (e.g. via PayPal)."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="payment_amount_positive"),
        CheckConstraint("from_member_id != to_member_id", name="payment_between_two_members"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    from_member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    to_member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    amount_cents: Mapped[int]
    date: Mapped[dt.date]
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)

    group: Mapped[Group] = relationship(back_populates="payments")
    from_member: Mapped[Member] = relationship(foreign_keys=[from_member_id])
    to_member: Mapped[Member] = relationship(foreign_keys=[to_member_id])

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_cents) / 100


class RecurringRule(Base):
    """A standing order: a fixed cost that is entered automatically every month.

    It is a copy of an expense (amount, category, payer, split) plus the day of
    the month and the date of the next booking.
    """

    __tablename__ = "recurring_rules"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="rule_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    payer_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(200))
    amount_cents: Mapped[int]
    category: Mapped[str | None] = mapped_column(String(50))
    # SplitMethod value; stored as text so PostgreSQL needs no second enum type
    split_method: Mapped[str] = mapped_column(String(20), default=SplitMethod.EQUAL.value)
    # [{"member_id": 3, "percent": null}, ...] – same meaning as ExpenseShare
    participants: Mapped[list] = mapped_column(JSON)
    day_of_month: Mapped[int]
    next_date: Mapped[dt.date]
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)

    group: Mapped[Group] = relationship(back_populates="recurring_rules")

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_cents) / 100


class RecurringDismissal(Base):
    """A description the group said is no fixed cost ("Keine Fixkosten")."""

    __tablename__ = "recurring_dismissals"
    __table_args__ = (UniqueConstraint("group_id", "key", name="one_dismissal_per_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    # Cleaned description (billbuddy.ml.recurring.model.description_key)
    key: Mapped[str] = mapped_column(String(200))
