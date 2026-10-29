"""Anomaly detection: duplicate entries and unusually high amounts.

Duplicates: the same amount and the same description (after cleaning:
"REWE Kartenzahlung" = "Rewe") at most one day apart – typically when two
people enter the same purchase.

Unusually high amounts: Tukey's fence on the log of the amount, per category:

    outlier if log(amount) > Q3 + 1.5 · IQR

    Q1, Q3 = quartiles of the log amounts of the category, IQR = Q3 − Q1

- log scale: amounts are skewed (many small, few large), on the log scale they
  are roughly symmetric
- quartiles instead of mean and standard deviation: the outliers themselves
  would pull the mean up and widen the standard deviation, so they would hide
  themselves ("masking"); quartiles stay put
- only high amounts count: a cheap purchase is no reason to worry
The evaluation (docs/anomaly-report.md) compared this with the z-score, the
robust z-score (median/MAD), the IQR rule on euros and an Isolation Forest;
it found the most outliers with the fewest false alarms.
"""

import datetime as dt
import math
from dataclasses import dataclass
from statistics import median, quantiles

from billbuddy.ml.categorizer.preprocessing import clean_description

MAX_DUPLICATE_DAYS = 1
IQR_FACTOR = 1.5
MIN_HISTORY = 8  # expenses needed in a category before it is checked
# Categories with always the same amount (rent): the IQR is 0, so compare with the median instead
FIXED_AMOUNT_FACTOR = 3


@dataclass(frozen=True)
class Entry:
    expense_id: int | None
    date: dt.date
    description: str
    amount_cents: int
    category: str | None


# --- Duplicates ---


def is_duplicate_pair(a: Entry, b: Entry) -> bool:
    key = clean_description(a.description)
    return (
        a.amount_cents == b.amount_cents
        and abs((a.date - b.date).days) <= MAX_DUPLICATE_DAYS
        and bool(key)
        and key == clean_description(b.description)
    )


def duplicates_of(candidate: Entry, entries: list[Entry]) -> list[Entry]:
    """Existing entries that look like the same purchase as `candidate`."""
    return [e for e in entries if e.expense_id != candidate.expense_id and is_duplicate_pair(candidate, e)]


def find_duplicates(entries: list[Entry]) -> list[tuple[Entry, Entry]]:
    """Pairs (earlier, later) of entries that look like the same purchase."""
    ordered = sorted(entries, key=lambda e: (e.date, e.expense_id or 0))
    pairs = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if (b.date - a.date).days > MAX_DUPLICATE_DAYS:
                break
            if is_duplicate_pair(a, b):
                pairs.append((a, b))
    return pairs


# --- Unusually high amounts ---


@dataclass
class OutlierCheck:
    is_outlier: bool
    typical_cents: int | None = None  # median amount in the category
    ratio: float | None = None  # amount / typical amount, e.g. 9.1 = "9 × as much as usual"


class OutlierModel:
    """Typical amounts per category, learned from the group's expenses."""

    def __init__(self, entries: list[Entry]):
        by_category: dict[str, list[float]] = {}
        for e in entries:
            if e.category and e.amount_cents > 0:
                by_category.setdefault(e.category, []).append(e.amount_cents)
        self.stats = {}
        for category, amounts in by_category.items():
            if len(amounts) < MIN_HISTORY:
                continue
            q1, _, q3 = quantiles([math.log(a) for a in amounts], n=4, method="inclusive")
            self.stats[category] = (q3 + IQR_FACTOR * (q3 - q1), q3 > q1, round(median(amounts)))

    def check(self, category: str | None, amount_cents: int) -> OutlierCheck:
        if category not in self.stats or amount_cents <= 0:
            return OutlierCheck(False)
        fence, varies, typical = self.stats[category]
        ratio = round(amount_cents / typical, 1)
        if not varies:
            return OutlierCheck(amount_cents > FIXED_AMOUNT_FACTOR * typical, typical, ratio)
        return OutlierCheck(math.log(amount_cents) > fence, typical, ratio)


def find_outliers(entries: list[Entry]) -> list[tuple[Entry, OutlierCheck]]:
    model = OutlierModel(entries)
    checks = [(e, model.check(e.category, e.amount_cents)) for e in entries]
    return [(e, c) for e, c in checks if c.is_outlier]
