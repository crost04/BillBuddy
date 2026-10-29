"""Month-end forecast: how much will be spent by the end of the month?

Method ("spent so far + typical rest"):

    forecast = spent until today + median of what was spent after the same day
               in the previous months (up to 6)

Why this works better than simply extrapolating ("spent / day × 30"): spending
is not spread evenly. Rent is paid on the 1st, subscriptions on fixed days. The
previous months show how much typically still comes after today – including
fixed costs that are still due. The median is robust against single unusual
months (e.g. a holiday). The range is ± one standard deviation of that rest.
The evaluation (docs/forecast-report.md) compares this with other methods.
"""

import calendar
import datetime as dt
from dataclasses import dataclass, field
from statistics import mean, median, pstdev

HISTORY_MONTHS = 6


@dataclass(frozen=True)
class Record:
    date: dt.date
    category: str | None
    amount_cents: int


@dataclass
class Forecast:
    category: str | None  # None in a per-category row = expenses without category
    spent_cents: int
    # Empty for past months (they are complete) and without any history
    forecast_cents: int | None = None
    low_cents: int | None = None
    high_cents: int | None = None
    # Mean total of the history months, for "more or less than usual?"
    average_cents: int | None = None


@dataclass
class MonthForecast:
    month: str  # "YYYY-MM"
    is_current: bool
    day: int  # forecast made at the end of this day
    days_in_month: int
    history_months: list[str]
    total: Forecast
    categories: list[Forecast] = field(default_factory=list)


def forecast_month(records: list[Record], today: dt.date, month: str | None = None) -> MonthForecast:
    """Forecast for `month` (default: the month of `today`), as seen at the end of `today`."""
    year, month_number = map(int, (month or today.strftime("%Y-%m")).split("-"))
    days_in_month = calendar.monthrange(year, month_number)[1]
    is_current = (year, month_number) == (today.year, today.month)
    # For a past month everything is known; the "day" is its last day
    day = today.day if is_current else days_in_month
    key = f"{year:04d}-{month_number:02d}"

    history = history_months(records, key)
    total = _forecast(records, None, key, day, history, is_current, all_categories=True)
    categories = sorted({r.category for r in records if _month(r.date) in (key, *history)}, key=str)
    rows = [_forecast(records, c, key, day, history, is_current) for c in categories]
    rows.sort(key=lambda f: f.forecast_cents if f.forecast_cents is not None else f.spent_cents, reverse=True)
    return MonthForecast(key, is_current, day, days_in_month, history, total, rows)


def _forecast(records, category, month, day, history, is_current, all_categories=False) -> Forecast:
    selected = [r for r in records if all_categories or r.category == category]
    spent = spent_until(selected, month, day)
    result = Forecast(category, spent)
    if not history:
        return result

    totals = [spent_until(selected, h, 31) for h in history]
    result.average_cents = round(mean(totals))
    if not is_current:
        return result

    # What was spent after `day` in each history month
    rests = [total - spent_until(selected, h, day) for h, total in zip(history, totals)]
    typical, spread = median(rests), pstdev(rests)
    result.forecast_cents = spent + round(typical)
    result.low_cents = spent + round(max(typical - spread, 0))
    result.high_cents = spent + round(typical + spread)
    return result


def history_months(records: list[Record], month: str) -> list[str]:
    """Up to 6 complete months before `month`.

    The first month with expenses is left out, because the group probably did
    not start on the 1st, so that month would look too cheap.
    """
    months = sorted({_month(r.date) for r in records})
    if not months:
        return []
    first = months[0]
    candidates = [m for m in _months_between(first, month) if m != first]
    return candidates[-HISTORY_MONTHS:]


def _months_between(start: str, end: str) -> list[str]:
    """All months from start (inclusive) to end (exclusive), also months without expenses."""
    year, month_number = map(int, start.split("-"))
    result = []
    while f"{year:04d}-{month_number:02d}" < end:
        result.append(f"{year:04d}-{month_number:02d}")
        year, month_number = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
    return result


def spent_until(records: list[Record], month: str, day: int) -> int:
    return sum(r.amount_cents for r in records if _month(r.date) == month and r.date.day <= day)


def _month(date: dt.date) -> str:
    return date.strftime("%Y-%m")
