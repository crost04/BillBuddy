"""Evaluation of the receipt parser on synthetic receipts with simulated OCR noise
(CRISP-DM). Writes docs/receipt-report.md.

Usage: python -m billbuddy.ml.receipt_ocr.evaluate
"""

import datetime as dt
import random
import re
from dataclasses import replace
from statistics import mean

from billbuddy.db import PROJECT_ROOT
from billbuddy.ml.receipt_ocr.combine import combine
from billbuddy.ml.receipt_ocr.parser import clean_line, parse_receipt
from billbuddy.ml.receipt_ocr.synthetic import generate_receipt, ocr_noise

REPORT_PATH = PROJECT_ROOT / "docs" / "receipt-report.md"
TODAY = dt.date(2026, 10, 29)
RECEIPTS = 400
SEED = 42
NOISE_LEVELS = (0.0, 0.01, 0.03, 0.05, 0.10)
# Independent noisy readings per receipt for the ensemble (the phone reads a photo up to four times)
READINGS = 3
# Results of the first parser version (commit 82906e9), before the improvements described in section 3
FIRST_VERSION = {0.01: (94.5, 98.2), 0.03: (84.8, 91.5), 0.05: (79.0, 83.0), 0.10: (62.5, 69.8)}  # (total, date)


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def percent(value: float) -> str:
    return f"{value * 100:.1f} %"


def baseline_total_largest(text: str) -> int | None:
    """Naive idea: the largest amount on the receipt is the total."""
    amounts = [round(float(a.replace(",", ".")) * 100) for a in re.findall(r"\d+[.,]\d{2}", text)]
    return max(amounts) if amounts else None


def baseline_store_first_line(text: str) -> str | None:
    lines = [clean_line(line) for line in text.splitlines() if line.strip()]
    return lines[0].title() if lines else None


def items_f1(predicted, truth) -> float:
    """Items are matched by amount (names differ through OCR noise)."""
    remaining = [t.amount_cents for t in truth]
    hits = 0
    for p in predicted:
        if p.amount_cents in remaining:
            remaining.remove(p.amount_cents)
            hits += 1
    precision = hits / len(predicted) if predicted else 0
    recall = hits / len(truth) if truth else 0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0


def evaluate(level: float, digit_swaps: bool = True) -> dict:
    rng = random.Random(SEED)
    results = []
    for _ in range(RECEIPTS):
        receipt = generate_receipt(rng, TODAY)
        text = ocr_noise(receipt.text, level, rng, digit_swaps)
        parsed = parse_receipt(text, TODAY)
        results.append(
            {
                "store": parsed.store == receipt.store,
                "store_baseline": baseline_store_first_line(text) == receipt.store,
                "date": parsed.date == receipt.date,
                "total": parsed.total_cents == receipt.total_cents,
                "total_baseline": baseline_total_largest(text) == receipt.total_cents,
                "items_f1": items_f1(parsed.items, receipt.items),
                "sum_matches": parsed.items_match_total,
                "sum_matches_correct": parsed.items_match_total and parsed.total_cents == receipt.total_cents,
            }
        )
    return {key: mean(r[key] for r in results) for key in results[0]}


def evaluate_readings(level: float) -> dict:
    """Several noisy readings of every receipt, combined like the server does: the best
    reading alone vs with the exact-sum repair. "wrong_match": the items add up to the
    right total but are not the receipt's items – the risk of the repair."""
    rng = random.Random(SEED)
    results = []
    for _ in range(RECEIPTS):
        receipt = generate_receipt(rng, TODAY)
        readings = [parse_receipt(ocr_noise(receipt.text, level, rng), TODAY) for _ in range(READINGS)]
        repaired, index = combine(readings)
        best = replace(readings[index], total_cents=repaired.total_cents, store=repaired.store, date=repaired.date)
        truth = sorted(i.amount_cents for i in receipt.items)
        row = {}
        for name, parsed in (("best", best), ("repaired", repaired)):
            matches = parsed.items_match_total and parsed.total_cents == receipt.total_cents
            row[f"{name}_f1"] = items_f1(parsed.items, receipt.items)
            row[f"{name}_match"] = matches
            row[f"{name}_wrong_match"] = matches and sorted(i.amount_cents for i in parsed.items) != truth
        results.append(row)
    return {key: mean(r[key] for r in results) for key in results[0]}


def main() -> None:
    rng = random.Random(SEED)
    example = generate_receipt(rng, TODAY)
    noisy_example = ocr_noise(example.text, 0.05, random.Random(SEED))
    scores = {level: evaluate(level) for level in NOISE_LEVELS}
    ensemble = {level: evaluate_readings(level) for level in (0.03, 0.05, 0.10)}
    # Section 3 compares with the first version, which was measured without look-alike digits
    first_noise = {level: evaluate(level, digit_swaps=False) for level in FIRST_VERSION}

    report = [
        "# Receipt scan – evaluation report",
        "",
        f"Generated by `python -m billbuddy.ml.receipt_ocr.evaluate` on {dt.date.today()}: "
        f"{RECEIPTS} synthetic receipts per noise level (random seed {SEED}).",
        "",
        "## 1. Data understanding and preparation",
        "",
        "No real receipts are available yet (cold start). `synthetic.py` generates receipts in the layouts of "
        "German shop types (Rewe/Edeka style, Lidl/Rossmann style, Aldi/Penny style, dm style, bakery) with quantity "
        'lines ("2 Stk x 0,59"), deposit, discounts, cash payment with change, VAT lines and two date formats. The '
        'dm style prints the tax rate as a digit behind the price ("2,45 1"), the quantity in front of the name '
        '("3x 0,85 Fruchtgummi") and a subtotal with a discount below it. '
        '`ocr_noise` then simulates typical text-recognition mistakes: confused characters (0↔O, 1↔l, 5↔S, ","→"."), '
        "look-alike digits (3↔2, 5↔9, 6↔8 – seen on real receipts, no rule can repair them), missing or extra "
        "spaces and lost lines. Noise level = probability per character.",
        "",
        "Example (noise 5 %):",
        "",
        "```",
        noisy_example,
        "```",
        "",
        "## 2. Results",
        "",
        table(
            ["Noise", "Store", "Date", "Total", "Items (F1)", "Items add up to the total"],
            [
                [
                    percent(level),
                    percent(s["store"]),
                    percent(s["date"]),
                    percent(s["total"]),
                    percent(s["items_f1"]),
                    percent(s["sum_matches"]),
                ]
                for level, s in scores.items()
            ],
        ),
        "",
        "Without noise the parser is almost perfect. With growing noise the store and the date suffer first: a "
        "single wrong character breaks a date, and a lost header line loses the store. The total holds up best "
        "because its keyword is matched tolerantly (see section 3).",
        "",
        "## 3. Iteration: what the first evaluation changed",
        "",
        'The first parser version broke down with noise: OCR split "SUMME" into "S UMME" or turned it into '
        '"SUMMC", so the total line was not found, and dates like "28.1O.2O26" were not repaired. Improvements: '
        "keywords are compared without spaces and with one wrong letter allowed; date-shaped text gets the same "
        "digit repair as amounts; shop names are compared with confusable characters unified. (Both columns "
        "measured with the noise model of the first evaluation, without look-alike digits.)",
        "",
        table(
            ["Noise", "Total – first version", "Total – now", "Date – first version", "Date – now"],
            [
                [
                    percent(level),
                    f"{FIRST_VERSION[level][0]:.1f} %",
                    percent(first_noise[level]["total"]),
                    f"{FIRST_VERSION[level][1]:.1f} %",
                    percent(first_noise[level]["date"]),
                ]
                for level in FIRST_VERSION
            ],
        ),
        "",
        "## 4. Comparison with naive approaches",
        "",
        table(
            [
                "Noise",
                "Total: largest amount",
                "Total: keyword rules (chosen)",
                "Store: first line",
                "Store: known shops (chosen)",
            ],
            [
                [
                    percent(level),
                    percent(s["total_baseline"]),
                    percent(s["total"]),
                    percent(s["store_baseline"]),
                    percent(s["store"]),
                ]
                for level, s in scores.items()
            ],
        ),
        "",
        '- "Largest amount" fails whenever the customer paid cash: the money given is larger than the total.',
        '- "First line" fails for headers like "REWE Markt GmbH" or "dm-drogerie markt"; matching known shop '
        "names finds the shop also in noisy text.",
        "",
        "## 5. Built-in plausibility check",
        "",
        "If the items add up to the total, the scan is very likely complete. Share of receipts where this check "
        "passed **and** the total was right:",
        "",
        table(
            ["Noise", "Check passed", "Check passed and total right"],
            [
                [percent(level), percent(s["sum_matches"]), percent(s["sum_matches_correct"])]
                for level, s in scores.items()
            ],
        ),
        "",
        "When the check passes, the total is practically always right – so the app can tell the user whether "
        "to double-check the scan.",
        "",
        "## 6. Several readings and the exact-sum repair",
        "",
        f"The phone reads every photo several times; the server takes the items of the most plausible reading "
        f"and may then replace or add up to two items with what another reading saw in the same line – but only "
        f"if the items then add up to the total to the cent (`combine.py`). Here every receipt is read "
        f'{READINGS} times with independent noise. "Complete" = the items add up to the right total; '
        f'"complete but wrong" = they add up, yet are not the receipt\'s items (the risk of the repair).',
        "",
        table(
            [
                "Noise",
                "Items F1: best reading",
                "Items F1: with repair",
                "Complete: best reading",
                "Complete: with repair",
                "Complete but wrong: best / with repair",
            ],
            [
                [
                    percent(level),
                    percent(s["best_f1"]),
                    percent(s["repaired_f1"]),
                    percent(s["best_match"]),
                    percent(s["repaired_match"]),
                    f"{percent(s['best_wrong_match'])} / {percent(s['repaired_wrong_match'])}",
                ]
                for level, s in ensemble.items()
            ],
        ),
        "",
        "The repair turns many incomplete scans into complete ones, while the share of wrong scans that pass "
        "the check barely rises: the exact sum to the cent is a strict test that a wrong value rarely passes "
        "by chance. Independent noise is optimistic – real readings of one photo make similar mistakes – so "
        "the real gain is smaller (see docs/crisp-dm.md).",
        "",
        "## 7. Limits",
        "",
        "- Synthetic receipts are tidier than real photos (folds, shadows, faded thermal paper, tilted shots). "
        "The real accuracy has to be measured with real receipts. Two real receipts (photographed on a table, "
        "each in 4 photo variants) are evaluated in docs/crisp-dm.md: a discounter receipt with 28 item lines "
        "(26.75 of 28 items found, complete in 2 of 4 variants) and a drugstore receipt with 5 item lines "
        "(complete in all 4 variants); total, date and store were right in every variant.",
        "- Item names are kept as recognized; the evaluation matches items by amount.",
        "",
    ]

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nWritten to {REPORT_PATH}")


if __name__ == "__main__":
    main()
