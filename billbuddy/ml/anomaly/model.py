"""Anomaly detection: duplicate entries and unusually high amounts.

Duplicates: the same amount and the same description (after cleaning:
"REWE Kartenzahlung" = "Rewe") at most one day apart – typically when two
people enter the same purchase.

Unusually high amounts: robust z-score of the amount within its category
(Iglewicz & Hoaglin):

    z = 0.6745 · (log(amount) − median) / MAD      outlier if z > 3.5

- log scale: amounts are skewed (many small, few large), on the log scale they
  are roughly symmetric
- median and MAD (median absolute deviation) instead of mean and standard
  deviation: the outliers themselves would pull the mean up and widen the
  standard deviation, so they would hide themselves ("masking")
- only high amounts count: a cheap purchase is no reason to worry
The evaluation (docs/anomaly-report.md) compares this with other methods.
"""

import datetime as dt
import math
from dataclasses import dataclass
from statistics import median

from billbuddy.ml.categorizer.preprocessing import clean_description

MAX_DUPLICATE_DAYS = 1
Z_THRESHOLD = 3.5
MIN_HISTORY = 8  # expenses needed in a category before it is checked
# Categories with always the same amount (rent): MAD is 0, so compare with the median instead
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
        for b in ordered[i + 1:]:
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
    score: float | None = None  # robust z-score


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
            logs = [math.log(a) for a in amounts]
            center = median(logs)
            mad = median(abs(x - center) for x in logs)
            self.stats[category] = (center, mad, round(median(amounts)))

    def check(self, category: str | None, amount_cents: int) -> OutlierCheck:
        if category not in self.stats or amount_cents <= 0:
            return OutlierCheck(False)
        center, mad, typical = self.stats[category]
        if mad == 0:
            return OutlierCheck(amount_cents > FIXED_AMOUNT_FACTOR * typical, typical)
        score = 0.6745 * (math.log(amount_cents) - center) / mad
        return OutlierCheck(score > Z_THRESHOLD, typical, round(score, 2))


def find_outliers(entries: list[Entry]) -> list[tuple[Entry, OutlierCheck]]:
    model = OutlierModel(entries)
    checks = [(e, model.check(e.category, e.amount_cents)) for e in entries]
    return [(e, c) for e, c in checks if c.is_outlier]
