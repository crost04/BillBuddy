"""Synthetic receipts for evaluating the parser (cold start: no real receipts yet).

Each receipt imitates the layout of a German shop type and comes with the
truth (store, date, total, items). `ocr_noise` then adds the kind of mistakes
text recognition makes on photos, in adjustable strength.
"""

import datetime as dt
import random
from dataclasses import dataclass, field

PRODUCTS = {
    "groceries": [
        ("Bananen", 99, 249),
        ("Vollmilch 3,5%", 99, 159),
        ("Brötchen", 29, 69),
        ("Gouda jung", 179, 329),
        ("Spaghetti", 89, 199),
        ("Tomaten", 129, 299),
        ("Butter", 179, 259),
        ("Joghurt Natur", 49, 99),
        ("Äpfel Elstar", 199, 349),
        ("Kaffee", 449, 899),
        ("Mineralwasser", 19, 69),
        ("Haferflocken", 59, 129),
        ("Bio Eier 10 Stk", 279, 399),
        ("Paprika rot", 99, 199),
        ("Toastbrot", 99, 179),
        ("Rhabarber", 199, 299),
    ],
    "drugstore": [
        ("Zahnpasta", 95, 295),
        ("Shampoo", 145, 495),
        ("Duschgel", 95, 345),
        ("Toilettenpapier", 245, 495),
        ("Spülmittel", 85, 195),
        ("Deo", 165, 395),
        ("Wattepads", 65, 145),
    ],
    "bakery": [
        ("Brezel", 70, 110),
        ("Roggenbrot", 299, 459),
        ("Croissant", 99, 149),
        ("Kaffee to go", 220, 380),
        ("Apfelkuchen", 250, 390),
    ],
}

# store name (truth), header lines, product type, layout style
STORES = [
    ("Rewe", ["REWE Markt GmbH", "Musterstraße 12", "90402 Nürnberg"], "groceries", "rewe"),
    ("Edeka", ["EDEKA Schmidt", "Hauptstr. 5", "91054 Erlangen"], "groceries", "rewe"),
    ("Lidl", ["LIDL", "Lidl sagt Danke"], "groceries", "lidl"),
    ("Aldi Süd", ["ALDI SÜD", "Filiale 0815"], "groceries", "aldi"),
    ("Penny", ["PENNY Markt", "Am Ring 3"], "groceries", "aldi"),
    ("dm", ["dm-drogerie markt", "Königstr. 40"], "drugstore", "drugstore"),
    ("Rossmann", ["ROSSMANN", "Ihr Drogeriemarkt"], "drugstore", "lidl"),
    ("Bäckerei Müller", ["BÄCKEREI MÜLLER", "seit 1952"], "bakery", "bakery"),
]


@dataclass
class TrueItem:
    name: str
    amount_cents: int


@dataclass
class SyntheticReceipt:
    text: str
    store: str
    date: dt.date
    total_cents: int
    items: list[TrueItem] = field(default_factory=list)


def euro(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",")


def generate_receipt(rng: random.Random, today: dt.date) -> SyntheticReceipt:
    store, header, kind, style = rng.choice(STORES)
    date = today - dt.timedelta(days=rng.randint(0, 60))
    lines = list(header)
    items = []

    for name, low, high in rng.sample(PRODUCTS[kind], k=min(len(PRODUCTS[kind]), rng.randint(2, 9))):
        unit = rng.randint(low, high)
        quantity = rng.choice([1, 1, 1, 2, 3])
        amount = unit * quantity
        shown = name.upper() if style in ("rewe", "aldi") else name
        if style == "drugstore":
            # quantity and unit price in front of the name, the tax rate as a digit behind the price
            shown = f"{quantity}x {euro(unit)} {name}" if quantity > 1 else name
            lines.append(f"{shown:<30}{euro(amount):>6} {rng.choice('12')}")
        elif style == "bakery":
            lines.append(f"{shown} {euro(amount)}")
        else:
            lines.append(f"{shown:<22}{euro(amount):>7} {rng.choice('AB')}")
        if quantity > 1 and style != "drugstore":
            lines.append(f"   {quantity} Stk x {euro(unit)}")
        items.append(TrueItem(shown.title() if shown.isupper() else shown, amount))
    if kind == "groceries" and rng.random() < 0.4:
        lines.append(f"{'PFAND 0,25' if style != 'lidl' else 'Pfand':<22}{euro(25):>7} A")
        items.append(TrueItem("Pfand", 25))
    if style == "lidl" and rng.random() < 0.5:
        lines.append(f"{'Rabatt':<22}{euro(-50):>7} A")
        items.append(TrueItem("Rabatt", -50))
    if style == "drugstore" and rng.random() < 0.5:
        # the subtotal of the items, then a discount on one of them
        lines.append(f"{'Zwischensumme':<30}{euro(sum(i.amount_cents for i in items)):>6}")
        discount = -round(rng.choice(items).amount_cents * 0.3)
        lines.append(f"{'Sonderartikelrabatt 30 %':<30}{euro(discount):>6}")
        items.append(TrueItem("Sonderartikelrabatt 30 %", discount))

    total = sum(i.amount_cents for i in items)
    total_label = {
        "rewe": "SUMME           EUR",
        "lidl": "zu zahlen",
        "aldi": "Summe",
        "drugstore": "SUMME EUR",
        "bakery": "Gesamt",
    }[style]
    lines += ["-" * 26, f"{total_label} {euro(total)}"]
    if rng.random() < 0.5:
        given = (total // 1000 + 1) * 1000
        lines += [f"Bar {euro(given)}", f"Rückgeld {euro(given - total)}"]
    else:
        lines.append(f"Geg. EC-Cash EUR {euro(total)}")
    if style in ("rewe", "aldi"):
        lines.append(f"MwSt 7% Netto {euro(round(total / 1.07))} MwSt {euro(total - round(total / 1.07))}")
    lines.append(
        f"Datum: {date:%d.%m.%Y} Uhrzeit: {rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}"
        if style != "lidl"
        else f"{date:%d.%m.%y} {rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}"
    )
    return SyntheticReceipt("\n".join(lines), store, date, total, items)


# Characters text recognition typically confuses on receipt photos
CONFUSIONS = {"0": "O", "1": "l", "5": "S", "8": "B", "O": "0", "l": "1", ",": ".", "e": "c", "a": "o", "u": "v"}


def ocr_noise(text: str, level: float, rng: random.Random) -> str:
    """Simulate OCR mistakes: confused characters, extra/missing spaces, lost lines."""
    lines = []
    for line in text.splitlines():
        if rng.random() < level / 2:
            continue  # line not recognized at all
        chars = []
        for c in line:
            r = rng.random()
            if r < level and c in CONFUSIONS:
                chars.append(CONFUSIONS[c])
            elif r < level * 1.3 and c == " ":
                continue
            else:
                chars.append(c)
                if rng.random() < level / 3:
                    chars.append(" ")
        lines.append("".join(chars))
    return "\n".join(lines)
