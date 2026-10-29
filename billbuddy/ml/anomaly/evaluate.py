"""Evaluation of the anomaly detection on the sample data (CRISP-DM).
Writes docs/anomaly-report.md.

The generator marks every inserted duplicate and outlier (is_duplicate,
is_outlier), so the methods can be checked against the truth.

Usage: python -m billbuddy.ml.anomaly.evaluate
"""

import csv
import dataclasses
import datetime as dt
import math
import random
from statistics import mean, median, pstdev

import numpy as np
from sklearn.ensemble import IsolationForest

from billbuddy.db import PROJECT_ROOT
from billbuddy.ml.anomaly import model
from billbuddy.ml.anomaly.model import Entry, OutlierModel, is_duplicate_pair
from billbuddy.ml.categorizer.training_data import SAMPLE_CSV

REPORT_PATH = PROJECT_ROOT / "docs" / "anomaly-report.md"
SEED = 42


@dataclasses.dataclass(frozen=True)
class Row:
    entry: Entry
    is_duplicate: bool
    is_outlier: bool


def load() -> list[Row]:
    with SAMPLE_CSV.open(encoding="utf-8") as file:
        return [
            Row(
                Entry(i, dt.date.fromisoformat(r["date"]), r["description"], int(r["amount_cents"]), r["category"]),
                r["is_duplicate"] == "True",
                r["is_outlier"] == "True",
            )
            for i, r in enumerate(csv.DictReader(file))
        ]


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def percent(value: float) -> str:
    return f"{value * 100:.1f} %"


def metrics(tp: int, fp: int, fn: int) -> list:
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return [tp, fp, fn, percent(precision), percent(recall), percent(f1)]


# --- Outliers ---


def by_category(rows: list[Row]) -> dict[str, list[Row]]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(r.entry.category, []).append(r)
    return {c: g for c, g in groups.items() if len(g) >= model.MIN_HISTORY}


def flag_zscore(amounts):
    m, s = mean(amounts), pstdev(amounts)
    return [s > 0 and (a - m) / s > 3 for a in amounts]


def flag_iqr(amounts):
    q1, q3 = np.quantile(amounts, [0.25, 0.75])
    return [a > q3 + 1.5 * (q3 - q1) and q3 > q1 for a in amounts]


def flag_iqr_log(amounts):
    return flag_iqr([math.log(a) for a in amounts])


def flag_isolation_forest(amounts):
    logs = np.log(np.array(amounts, dtype=float)).reshape(-1, 1)
    labels = IsolationForest(contamination="auto", random_state=SEED).fit_predict(logs)
    center = median(amounts)
    return [label == -1 and a > center for label, a in zip(labels, amounts)]  # only high amounts


def flag_robust_z(amounts, threshold=3.5):
    logs = [math.log(a) for a in amounts]
    center = median(logs)
    mad = median(abs(x - center) for x in logs)
    return [mad > 0 and 0.6745 * (x - center) / mad > threshold for x in logs]


def flag_chosen(rows):
    outlier_model = OutlierModel([r.entry for r in rows])
    return [outlier_model.check(r.entry.category, r.entry.amount_cents).is_outlier for r in rows]


def amounts_of(rows):
    return [r.entry.amount_cents for r in rows]


OUTLIER_METHODS = {
    "z-score (mean and standard deviation) > 3": lambda rows: flag_zscore(amounts_of(rows)),
    "IQR rule on euros (Q3 + 1.5 · IQR)": lambda rows: flag_iqr(amounts_of(rows)),
    "Isolation Forest (scikit-learn) on log amounts": lambda rows: flag_isolation_forest(amounts_of(rows)),
    "Robust z-score (median, MAD) on log amounts > 3.5": lambda rows: flag_robust_z(amounts_of(rows)),
    "Robust z-score on log amounts > 3.0": lambda rows: flag_robust_z(amounts_of(rows), 3.0),
    "IQR rule on log amounts (chosen)": flag_chosen,
}


def evaluate_outliers(rows: list[Row], method) -> list:
    tp = fp = fn = 0
    for group in by_category(rows).values():
        for r, flagged in zip(group, method(group)):
            tp += flagged and r.is_outlier
            fp += flagged and not r.is_outlier
            fn += r.is_outlier and not flagged
    return metrics(tp, fp, fn)


# --- Duplicates ---


def realistic_duplicates(rows: list[Row]) -> list[Row]:
    """The second person writes the purchase differently and maybe one day later."""
    rng = random.Random(SEED)
    result = []
    for r in rows:
        if r.is_duplicate:
            text = rng.choice([r.entry.description.upper(), r.entry.description.lower(),
                               f"{r.entry.description} Kartenzahlung", r.entry.description])
            entry = dataclasses.replace(r.entry, description=text, date=r.entry.date + dt.timedelta(days=rng.choice([0, 1])))
            r = dataclasses.replace(r, entry=entry)
        result.append(r)
    return result


DUPLICATE_METHODS = {
    "Exactly the same description, amount and date": lambda a, b: (
        a.description == b.description and a.amount_cents == b.amount_cents and a.date == b.date
    ),
    "Same amount within 1 day (description ignored)": lambda a, b: (
        a.amount_cents == b.amount_cents and abs((a.date - b.date).days) <= 1
    ),
    "Same cleaned description and amount within 1 day (chosen)": is_duplicate_pair,
}


def evaluate_duplicates(rows: list[Row], same) -> list:
    ordered = sorted(rows, key=lambda r: r.entry.date)
    found_pairs = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if (b.entry.date - a.entry.date).days > 1:
                break
            if same(a.entry, b.entry):
                found_pairs.append((a, b))
    tp = sum(a.is_duplicate or b.is_duplicate for a, b in found_pairs)
    fp = len(found_pairs) - tp
    detected = {id(r) for pair in found_pairs for r in pair if r.is_duplicate}
    fn = sum(r.is_duplicate and id(r) not in detected for r in rows)
    return metrics(tp, fp, fn)


def main() -> None:
    rows = load()
    without_duplicates = [r for r in rows if not r.is_duplicate]
    outliers = [r for r in without_duplicates if r.is_outlier]
    groups = by_category(without_duplicates)
    # True outliers that are still smaller than the largest normal expense of their category
    unchecked = sum(r.entry.category not in groups for r in outliers)
    hidden = sum(
        r.entry.amount_cents <= max(x.entry.amount_cents for x in groups[r.entry.category] if not x.is_outlier)
        for r in outliers
        if r.entry.category in groups
    )
    headers = ["Method", "Found (correct)", "False alarms", "Missed", "Precision", "Recall", "F1"]

    report = [
        "# Anomaly detection – evaluation report",
        "",
        f"Generated by `python -m billbuddy.ml.anomaly.evaluate` on {dt.date.today()} (sample data). "
        "The generator inserted duplicates and unusually high amounts (4–8 × the normal amount) and marked them.",
        "",
        "## 1. Data understanding",
        "",
        f"- {len(rows)} expenses, of which {sum(r.is_duplicate for r in rows)} are duplicates and "
        f"{len(outliers)} are unusually high.",
        f"- {hidden} of the {len(outliers)} unusually high amounts are still smaller than the largest normal "
        "expense of their category (e.g. a 4 × grocery bill in a category where big shopping trips happen). "
        "No method that only looks at the amount can find those.",
        f"- {unchecked} unusually high amount(s) are in categories with fewer than {model.MIN_HISTORY} expenses "
        "(e.g. travel), which are not checked: too little data to know what is normal.",
        "- Amounts are skewed: many small, few large expenses. On the log scale they are roughly symmetric.",
        "",
        "## 2. Unusually high amounts – method comparison",
        "",
        "Each category is checked separately (a 300 € grocery bill is unusual, a 300 € hotel is not); "
        f"categories with fewer than {model.MIN_HISTORY} expenses are skipped.",
        "",
        table(headers, [[name, *evaluate_outliers(without_duplicates, method)] for name, method in OUTLIER_METHODS.items()]),
        "",
        "- Mean and standard deviation are pulled up by the outliers themselves (masking), so they miss some "
        "and still raise false alarms.",
        "- The IQR rule on euros raises many false alarms, because large amounts are normal in a skewed distribution.",
        "- The Isolation Forest is a machine-learning method; with its default setting it flags far too much. It "
        "would need the share of outliers in advance – which nobody knows in real use – and for a single number "
        "(the amount) it brings no advantage over simple statistics.",
        "- The robust z-score with the value recommended in the literature (3.5) raises no false alarm but misses "
        "half of the outliers; with 3.0 it is close to the IQR rule.",
        "- **Chosen: the IQR rule on log amounts** – the most outliers found with the fewest false alarms. We had "
        "first picked the robust z-score; the evaluation showed it was not the best choice for this data.",
        "",
        "## 3. Threshold of the chosen method",
        "",
    ]

    rows_for_threshold = []
    original = model.IQR_FACTOR
    for factor in (1.0, 1.5, 2.0, 3.0):
        model.IQR_FACTOR = factor
        rows_for_threshold.append([f"{factor}" + (" (used)" if factor == original else ""),
                                   *evaluate_outliers(without_duplicates, flag_chosen)])
    model.IQR_FACTOR = original
    report += [
        table(["Factor k in Q3 + k · IQR", *headers[1:]], rows_for_threshold),
        "",
        "1.5 is the usual value (Tukey). A smaller factor raises more false alarms – and every false alarm asks "
        "the user a needless question; a larger one misses outliers.",
        "",
        "## 4. Duplicates – method comparison",
        "",
        "Evaluated per pair. Left: the duplicates exactly as generated (identical copies). Right: more "
        "realistic – the second person writes the purchase differently (\"REWE\", \"rewe Kartenzahlung\") "
        "and maybe one day later.",
        "",
        "Identical copies:",
        "",
        table(headers, [[name, *evaluate_duplicates(rows, same)] for name, same in DUPLICATE_METHODS.items()]),
        "",
        "Realistic duplicates:",
        "",
        table(headers, [[name, *evaluate_duplicates(realistic_duplicates(rows), same)]
                        for name, same in DUPLICATE_METHODS.items()]),
        "",
        "- An exact comparison misses duplicates as soon as the spelling or the date differs.",
        "- Ignoring the description works just as well here – but only because the generated amounts have random "
        "cents, so two different purchases never cost exactly the same. Real amounts are often round (two "
        "10 € cinema tickets on consecutive days), which would cause false alarms. That is why the chosen method "
        "also compares the cleaned description; whether this matters will show with real data.",
        "",
    ]

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nWritten to {REPORT_PATH}")


if __name__ == "__main__":
    main()
