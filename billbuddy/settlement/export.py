"""Export of a group's expenses and payments as a CSV file – the backup of the data.

The file uses the German spreadsheet format, so it opens directly in Excel or
Numbers: ";" between columns, "," as decimal separator, and a byte order mark
so umlauts are shown correctly.
"""

import csv
import io

from billbuddy.expenses.categories import CATEGORY_LABELS_DE
from billbuddy.expenses.models import Group, SplitMethod
from billbuddy.settlement.calculator import expense_shares

HEADER = [
    "Datum",
    "Art",
    "Beschreibung",
    "Betrag",
    "Kategorie",
    "Bezahlt von",
    "Fixkosten",
    "Jeden Monat automatisch",
    "Aufteilung",
    "Anteile",
]
SPLIT_NAMES = {SplitMethod.EQUAL: "gleich", SplitMethod.PERCENT: "Prozent", SplitMethod.INCOME: "Einkommen"}


def euro(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",")


def group_csv(group: Group) -> str:
    names = {m.id: m.name for m in group.members}
    rows = []
    for e in group.expenses:
        shares = "; ".join(f"{names[member_id]} {euro(cents)} €" for member_id, cents in expense_shares(e).items())
        rows.append(
            [
                e.date.isoformat(),
                "Ausgabe",
                e.description,
                euro(e.amount_cents),
                CATEGORY_LABELS_DE.get(e.category, ""),
                names[e.payer_id],
                "ja" if e.is_fixed else "nein",
                "ja" if e.recurring_rule_id else "nein",
                SPLIT_NAMES[e.split_method],
                shares,
            ]
        )
    for p in group.payments:
        rows.append(
            [
                p.date.isoformat(),
                "Ausgleichszahlung",
                f"{names[p.from_member_id]} → {names[p.to_member_id]}",
                euro(p.amount_cents),
                "",
                names[p.from_member_id],
                "nein",
                "nein",
                "",
                f"an {names[p.to_member_id]}",
            ]
        )
    rows.sort(key=lambda row: row[0])  # oldest first, as in a bank statement

    output = io.StringIO()
    output.write("﻿")  # byte order mark: tells Excel that the file is UTF-8 (umlauts)
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return output.getvalue()
