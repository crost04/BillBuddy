"""Recurring-cost detection: expenses that come back every month with a similar amount.

Statistical rules instead of a trained model (see docs/recurring-report.md):
- the same description, after cleaning ("Miete Oktober" and "MIETE November" -> "miete")
- at least 3 times
- a regular gap of about one month: median 26–35 days, and the gaps hardly vary
  (standard deviation at most 5 days – payments move a little because of weekends)
- a similar amount: coefficient of variation (standard deviation / mean) at most 15 %

Groceries at the same shop come back often too, but at irregular gaps and with
changing amounts, so the last two rules sort them out.
"""

import calendar
import datetime as dt
from dataclasses import dataclass, field
from statistics import mean, median, pstdev

from billbuddy.ml.categorizer.preprocessing import clean_description

MIN_COUNT = 3
MONTHLY_GAP_DAYS = (26, 35)
MAX_GAP_STD_DAYS = 5
MAX_AMOUNT_CV = 0.15

MONTH_WORDS = {
    "januar",
    "februar",
    "märz",
    "maerz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
    "jan",
    "feb",
    "mär",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "okt",
    "nov",
    "dez",
}


def description_key(description: str) -> str:
    """Key that is the same for every payment of a series ("Miete Oktober" -> "miete")."""
    return " ".join(w for w in clean_description(description).split() if w not in MONTH_WORDS)


@dataclass(frozen=True)
class Item:
    expense_id: int | None
    date: dt.date
    description: str
    amount_cents: int
    is_fixed: bool = False


@dataclass
class RecurringSeries:
    key: str
    description: str  # the most recent description, as the user wrote it
    count: int
    typical_amount_cents: int
    interval_days: float
    day_of_month: int
    last_date: dt.date
    next_date: dt.date
    # Still running? A cancelled subscription stops appearing.
    active: bool
    # True if every payment of the series is already marked as fixed cost
    already_fixed: bool
    expense_ids: list[int] = field(default_factory=list)


def find_recurring(items: list[Item], today: dt.date) -> list[RecurringSeries]:
    groups: dict[str, list[Item]] = {}
    for item in items:
        key = description_key(item.description)
        if key:
            groups.setdefault(key, []).append(item)

    result = []
    for key, series in groups.items():
        series.sort(key=lambda i: i.date)
        if is_recurring(series):
            result.append(_describe(key, series, today))
    result.sort(key=lambda s: s.typical_amount_cents, reverse=True)
    return result


def is_recurring(series: list[Item]) -> bool:
    """Apply the rules to the payments of one description (sorted by date)."""
    if len(series) < MIN_COUNT:
        return False
    gaps = [(b.date - a.date).days for a, b in zip(series, series[1:], strict=False)]
    amounts = [i.amount_cents for i in series]
    low, high = MONTHLY_GAP_DAYS
    return (
        low <= median(gaps) <= high
        and pstdev(gaps) <= MAX_GAP_STD_DAYS
        and pstdev(amounts) / mean(amounts) <= MAX_AMOUNT_CV
    )


def _describe(key: str, series: list[Item], today: dt.date) -> RecurringSeries:
    gaps = [(b.date - a.date).days for a, b in zip(series, series[1:], strict=False)]
    interval = median(gaps)
    day = round(median(i.date.day for i in series))
    last = series[-1].date
    return RecurringSeries(
        key=key,
        description=series[-1].description,
        count=len(series),
        typical_amount_cents=round(median(i.amount_cents for i in series)),
        interval_days=interval,
        day_of_month=day,
        last_date=last,
        next_date=_next_month(last, day),
        # Missed more than one payment -> probably cancelled
        active=(today - last).days <= interval * 1.5 + 5,
        already_fixed=all(i.is_fixed for i in series),
        expense_ids=[i.expense_id for i in series if i.expense_id is not None],
    )


def _next_month(date: dt.date, day: int) -> dt.date:
    year, month = (date.year + 1, 1) if date.month == 12 else (date.year, date.month + 1)
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))
