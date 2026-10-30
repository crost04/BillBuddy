"""Combine several OCR readings of the same receipt photo into one result.

The phone reads every photo several times (other page modes, other image
preparation), and each reading loses or misreads different lines. Like a vote
between several readers (an ensemble):

- total, store and date: the value most readings agree on, so a single
  misread total ("81250" instead of "12,50") is outvoted
- items: from the most plausible reading – the one whose items add up to the
  agreed total, otherwise the one with the most items

Taking single items from different readings was tried as well, but on a real
receipt it made the result worse (see docs/crisp-dm.md).
"""

from collections import Counter
from dataclasses import replace

from billbuddy.ml.receipt_ocr.parser import Receipt


def combine(readings: list[Receipt]) -> tuple[Receipt, int | None]:
    """The combined receipt and the index of the reading its items come from."""
    if not readings:
        return Receipt(), None
    agreed = {
        "total_cents": _vote([r.total_cents for r in readings]),
        "store": _vote([r.store for r in readings]),
        "date": _vote([r.date for r in readings]),
    }
    candidates = [replace(r, **agreed) for r in readings]
    best = max(range(len(candidates)), key=lambda i: _plausibility(candidates[i]))
    return candidates[best], best


def _vote(values):
    """The most common value; on a tie the one of the earlier reading."""
    counts = Counter(v for v in values if v is not None)
    return counts.most_common(1)[0][0] if counts else None


def _plausibility(receipt: Receipt) -> tuple:
    gap = abs(receipt.items_sum_cents - receipt.total_cents) if receipt.total_cents is not None else 0
    return (receipt.items_match_total, len(receipt.items), -gap)
