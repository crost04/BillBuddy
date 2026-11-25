"""Evaluation of the receipt scan on real receipt photos (CRISP-DM).

Real receipts contain personal data, so photos, true contents and recognized
texts stay in data/private/receipts/, which git ignores:

- truth/<id>.json: store, date, total and items in cents, and the set the
  receipt belongs to: "dev" (may be used to improve the rules) or "test"
  (held back, only for the final measurement – otherwise the rules would be
  tuned to exactly these photos)
- ocr/<version>/<id>_<n>.txt: the text of reading n, as the phone produces it
  (frontend/js/receipt.js run in a browser on the photo)

Like the phone, the evaluation stops reading as soon as the items add up to
the total, and it uses the current parser and combination of readings.

Usage: python -m billbuddy.ml.receipt_ocr.evaluate_real [version] [--set dev|test|all] [--details]
"""

import argparse
import datetime as dt
import json
from collections import Counter
from dataclasses import dataclass

from billbuddy.db import PROJECT_ROOT
from billbuddy.ml.receipt_ocr.combine import combine
from billbuddy.ml.receipt_ocr.parser import Receipt, letters_only, ocr_normalized, parse_receipt

RECEIPTS_DIR = PROJECT_ROOT / "data" / "private" / "receipts"
TODAY = dt.date(2026, 11, 25)


@dataclass
class Result:
    receipt_id: str
    truth: dict
    receipt: Receipt
    readings: int

    @property
    def item_hits(self) -> int:
        return sum((self._found & self._true).values())

    @property
    def missing(self) -> list[int]:
        return sorted((self._true - self._found).elements())

    @property
    def wrong(self) -> list[int]:
        return sorted((self._found - self._true).elements())

    @property
    def complete(self) -> bool:
        return self._found == self._true and self.total_right

    @property
    def total_right(self) -> bool:
        return self.receipt.total_cents == self.truth["total"]

    @property
    def date_right(self) -> bool | None:
        expected = self.truth["date"]
        return None if expected is None else str(self.receipt.date) == expected

    @property
    def store_right(self) -> bool:
        found = letters_only(ocr_normalized(self.receipt.store or ""))
        expected = letters_only(ocr_normalized(self.truth["store"]))
        return bool(found) and (expected in found or found in expected)

    @property
    def _found(self) -> Counter:
        return Counter(i.amount_cents for i in self.receipt.items)

    @property
    def _true(self) -> Counter:
        return Counter(i["cents"] for i in self.truth["items"])


def evaluate_receipt(receipt_id: str, truth: dict, version: str) -> Result:
    """The phone's procedure: read again until the items add up to the total."""
    readings = []
    for n in range(1, 10):
        path = RECEIPTS_DIR / "ocr" / version / f"{receipt_id}_{n}.txt"
        if not path.exists():
            break
        readings.append(parse_receipt(path.read_text(encoding="utf-8"), TODAY))
        if combine(readings)[0].items_match_total:
            break
    return Result(receipt_id, truth, combine(readings)[0], len(readings))


def evaluate(version: str, which: str) -> list[Result]:
    results = []
    for path in sorted((RECEIPTS_DIR / "truth").glob("*.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        if which in ("all", truth["split"]):
            results.append(evaluate_receipt(path.stem, truth, version))
    return results


def summary(results: list[Result]) -> dict:
    found = sum(len(r.receipt.items) for r in results)
    true = sum(len(r.truth["items"]) for r in results)
    hits = sum(r.item_hits for r in results)
    precision = hits / found if found else 0
    recall = hits / true if true else 0
    dated = [r for r in results if r.date_right is not None]
    return {
        "receipts": len(results),
        "total": sum(r.total_right for r in results),
        "date": f"{sum(r.date_right for r in dated)}/{len(dated)}",
        "store": sum(r.store_right for r in results),
        "items_found": f"{hits}/{true}",
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f1": round(2 * precision * recall / (precision + recall) * 100, 1) if hits else 0,
        "complete": sum(r.complete for r in results),
        # The app showed "✅ die Summe passt", but the items were not right
        "check_passed_but_wrong": sum(r.receipt.items_match_total and not r.complete for r in results),
        "readings": round(sum(r.readings for r in results) / len(results), 1) if results else 0,
    }


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("version", nargs="?", default="v1", help="folder in ocr/ with the recognized texts")
    args.add_argument("--set", default="dev", choices=["dev", "test", "all"])
    args.add_argument("--details", action="store_true", help="one line per receipt")
    options = args.parse_args()

    results = evaluate(options.version, options.set)
    if options.details:
        for r in results:
            flags = "".join(
                "✓" if ok else "✗" for ok in (r.total_right, r.date_right is not False, r.store_right, r.complete)
            )
            print(
                f"{r.receipt_id} {r.truth['store']:<10} total/date/store/complete {flags}  "
                f"items {r.item_hits}/{len(r.truth['items'])}  readings {r.readings}  "
                f"store={r.receipt.store!r}  missing={r.missing} wrong={r.wrong}"
            )
    print(json.dumps(summary(results), ensure_ascii=False))


if __name__ == "__main__":
    main()
