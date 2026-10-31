"""Combine several OCR readings of the same receipt photo into one result.

The phone reads every photo several times (other page modes, other image
preparation), and each reading loses or misreads different lines. Like a vote
between several readers (an ensemble):

- total, store and date: the value most readings agree on, so a single
  misread total ("81250" instead of "12,50") is outvoted
- items: from the most plausible reading – the one whose items add up to the
  agreed total, otherwise the one with the most items
- repair: if those items do not add up, up to two of them may be replaced by
  what another reading saw in the same line (or a line the best reading lost
  is added) – but only if the items then add up to the total to the cent.
  The receipt's own arithmetic is the check: a misread "1,40" is replaced by
  another reading's "2,40" because exactly 1,00 was missing.

Taking items from other readings *without* that exact check was tried first
and made the result worse (a misread amount that only brought the sum closer
was taken over; see docs/crisp-dm.md).
"""

from collections import Counter
from dataclasses import replace
from difflib import SequenceMatcher
from itertools import combinations

from billbuddy.ml.receipt_ocr.parser import Receipt, ReceiptItem, letters_only, ocr_normalized

MAX_CHANGES = 2
# Item names in two readings count as the same line from this similarity on (0..1)
SAME_LINE = 0.5


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
    others = [c for i, c in enumerate(candidates) if i != best]
    return repair(candidates[best], others), best


def repair(receipt: Receipt, others: list[Receipt]) -> Receipt:
    """Up to MAX_CHANGES items replaced or added from other readings, only if the
    items then match the total exactly. Fewer changes first; among several
    solutions the one most readings support; a tie changes nothing."""
    if receipt.total_cents is None or receipt.items_match_total or not receipt.items:
        return receipt
    support: Counter = Counter()  # change -> number of readings that saw it
    names = {}
    for other in others:
        pairs = _align(receipt.items, other.items)
        for j, item in enumerate(other.items):
            if j in pairs:
                if item.amount_cents != receipt.items[pairs[j]].amount_cents:
                    support[("set", pairs[j], item.amount_cents)] += 1
            else:
                # a line the best reading lost: insert it after the last aligned line above it
                position = max((pairs[k] + 1 for k in pairs if k < j), default=0)
                change = ("insert", position, item.amount_cents)
                support[change] += 1
                names.setdefault(change, item.name)
    gap = receipt.total_cents - receipt.items_sum_cents
    for size in range(1, MAX_CHANGES + 1):
        solutions = [
            changes
            for changes in combinations(support, size)
            if _one_value_per_item(changes) and _difference(receipt, changes) == gap
        ]
        if solutions:
            ranked = sorted((sum(support[c] for c in changes), changes) for changes in solutions)
            if len(ranked) > 1 and ranked[-1][0] == ranked[-2][0]:
                return receipt  # ambiguous: better a visible gap than a wrong guess
            return _apply(receipt, ranked[-1][1], names)
    return receipt


def _align(items: list[ReceiptItem], other: list[ReceiptItem]) -> dict[int, int]:
    """Which item of the other reading is which line of ours: {other index: our index}.
    Lines keep their order, so this is a longest common subsequence over similar names."""
    similar = [[_similarity(a.name, b.name) >= SAME_LINE for b in other] for a in items]
    n, m = len(items), len(other)
    longest = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if similar[i][j]:
                longest[i][j] = 1 + longest[i + 1][j + 1]
            else:
                longest[i][j] = max(longest[i + 1][j], longest[i][j + 1])
    pairs, i, j = {}, 0, 0
    while i < n and j < m:
        if similar[i][j] and longest[i][j] == 1 + longest[i + 1][j + 1]:
            pairs[j] = i
            i, j = i + 1, j + 1
        elif longest[i + 1][j] >= longest[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, letters_only(ocr_normalized(a)), letters_only(ocr_normalized(b))).ratio()


def _one_value_per_item(changes: tuple) -> bool:
    replaced = [c[1] for c in changes if c[0] == "set"]
    return len(replaced) == len(set(replaced))


def _difference(receipt: Receipt, changes: tuple) -> int:
    return sum(c[2] - (receipt.items[c[1]].amount_cents if c[0] == "set" else 0) for c in changes)


def _apply(receipt: Receipt, changes: tuple, names: dict) -> Receipt:
    items = list(receipt.items)
    for kind, index, cents in changes:
        if kind == "set":
            items[index] = ReceiptItem(items[index].name, cents)
    # insert from the bottom up, so the positions above stay right
    for change in sorted((c for c in changes if c[0] == "insert"), key=lambda c: c[1], reverse=True):
        items.insert(change[1], ReceiptItem(names[change], change[2]))
    return replace(receipt, items=items)


def _vote(values):
    """The most common value; on a tie the one of the earlier reading."""
    counts = Counter(v for v in values if v is not None)
    return counts.most_common(1)[0][0] if counts else None


def _plausibility(receipt: Receipt) -> tuple:
    gap = abs(receipt.items_sum_cents - receipt.total_cents) if receipt.total_cents is not None else 0
    return (receipt.items_match_total, len(receipt.items), -gap)
