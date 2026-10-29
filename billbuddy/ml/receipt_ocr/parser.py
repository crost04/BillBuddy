"""Turn the text of a receipt photo (from OCR) into store, date, total and items.

The text recognition itself (Tesseract.js) runs on the phone, so the photo never
leaves it; only the recognized text comes here. OCR text is noisy: "0" becomes
"O", "1" becomes "l", spaces appear inside numbers. So every line is cleaned
first, then rules find the parts:

- store: a known shop name in the first lines, otherwise the first line with words
- date: the first plausible date (not in the future, not older than two years)
- total: the line with "zu zahlen", "Summe", "Gesamt", ... and an amount
- items: lines above the total that end with an amount (skipping quantity
  lines like "2 Stk x 0,59", which belong to the line above)
"""

import datetime as dt
import re
from dataclasses import dataclass, field

from billbuddy.data.generator import VARIABLE_COSTS

AMOUNT = r"-?\d{1,4}[.,]\d{2}"
# An amount at the end of a line, optionally followed by "€"/"EUR" and a tax code (A, B, *)
LINE_AMOUNT = re.compile(rf"(?P<amount>{AMOUNT})\s*(?:€|EUR)?\s*(?:[A-Z*]{{1,2}})?\s*$")
DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
# Date-shaped text with letters OCR confuses with digits ("28.1O.2O26")
DATE_LIKE = re.compile(r"(?<![A-Za-z])[\dOoQlIiSB]{1,2}[./-][\dOoQlIiSB]{1,2}[./-][\dOoQlIiSB]{2,4}(?![A-Za-z])")
DIGIT_FIXES = str.maketrans("OoQlIiSB", "00011158")
# Lines that only explain the line above: "2 Stk x 0,59", "0,846 kg x 1,99 EUR/kg"
QUANTITY = re.compile(r"^\s*\d+([.,]\d+)?\s*(x|stk|st\b|kg)|\bx\s*\d+[.,]\d{2}\b|eur\s*/\s*kg", re.IGNORECASE)

# Total lines, best first ("Zwischensumme" is not the total)
TOTAL_WORDS = ["zu zahlen", "summe", "gesamtbetrag", "gesamt", "endbetrag", "total", "zahlbetrag", "betrag"]
# Lines below the items that are no items
NOT_ITEM_WORDS = [
    "summe", "gesamt", "zu zahlen", "total", "betrag", "mwst", "ust", "netto", "brutto", "steuer",
    "gegeben", "rückgeld", "rueckgeld", "wechselgeld", "bar", "ec-cash", "girocard", "kartenzahlung",
    "visa", "mastercard", "zahlung", "datum", "uhrzeit", "kasse", "bon-nr", "beleg",
]

KNOWN_STORES = sorted(
    {merchant for _, _, _, merchants in VARIABLE_COSTS.values() for merchant in merchants},
    key=len,
    reverse=True,  # "Aldi Süd" before "Aldi"
)
# Kinds of shops, not brands: "BÄCKEREI MÜLLER" should stay "Bäckerei Müller"
GENERIC_SHOPS = {
    "Bäckerei", "Metzgerei", "Wochenmarkt", "Pizzeria", "Café", "Döner", "Sushi Bar", "Biergarten", "Kino",
    "Konzert", "Bowling", "Schwimmbad", "Museum", "Kletterhalle", "Apotheke", "Optiker", "Zahnarzt",
    "Physiotherapie", "Hotel", "Ferienwohnung", "Geschenk", "Post", "Friseur", "Spende", "Blumen", "Parkhaus",
}


@dataclass
class ReceiptItem:
    name: str
    amount_cents: int


@dataclass
class Receipt:
    store: str | None = None
    date: dt.date | None = None
    total_cents: int | None = None
    items: list[ReceiptItem] = field(default_factory=list)

    @property
    def items_sum_cents(self) -> int:
        return sum(i.amount_cents for i in self.items)

    @property
    def items_match_total(self) -> bool:
        """True if the items add up to the total – a good sign that nothing was missed."""
        return self.total_cents is not None and bool(self.items) and abs(self.items_sum_cents - self.total_cents) <= 1


def parse_receipt(text: str, today: dt.date) -> Receipt:
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    total_index, total = find_total(lines)
    return Receipt(
        store=find_store(lines),
        date=find_date(lines, today),
        total_cents=total,
        items=find_items(lines[:total_index] if total_index is not None else lines),
    )


def clean_line(line: str) -> str:
    """Repair typical OCR mistakes in numbers and collapse spaces."""
    # Letters that OCR confuses with digits, but only inside number-like tokens ("1,2O" -> "1,20")
    def fix_token(match: re.Match) -> str:
        token = match.group(0)
        if not any(c.isdigit() for c in token):
            return token  # no digit at all: probably a word, leave it
        return token.translate(DIGIT_FIXES)

    line = re.sub(r"(?<![A-Za-zÄÖÜäöüß])[\dOoQlIiSB]+[.,][\dOoQlIiSB]{2}(?![A-Za-zÄÖÜäöüß])", fix_token, line)
    # "1, 29" or "1 ,29" -> "1,29"
    line = re.sub(r"(\d)\s*([.,])\s*(\d{2})(?!\d)", r"\1\2\3", line)
    return " ".join(line.split())


def find_store(lines: list[str]) -> str | None:
    for line in lines[:8]:
        lowered = _ocr_normalized(line)
        for store in KNOWN_STORES:
            if re.search(rf"(?<![a-zäöüß]){re.escape(_ocr_normalized(store))}(?![a-zäöüß])", lowered):
                if store in GENERIC_SHOPS and not _amount_at_end(line):
                    return _readable(line)
                return store
    for line in lines[:5]:
        letters = sum(c.isalpha() for c in line)
        if letters >= 3 and letters > len(line) / 2:
            return _readable(line)
    return None


def find_date(lines: list[str], today: dt.date) -> dt.date | None:
    candidates = []
    for line in lines:
        line = DATE_LIKE.sub(lambda m: m.group(0).translate(DIGIT_FIXES), line)
        for day, month, year in DATE.findall(line):
            year = int(year) + (2000 if len(year) == 2 else 0)
            try:
                date = dt.date(year, int(month), int(day))
            except ValueError:
                continue
            if today - dt.timedelta(days=730) <= date <= today + dt.timedelta(days=1):
                candidates.append((0 if "datum" in line.lower() else 1, date))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


CARD_PAYMENT_WORDS = ["ec-cash", "ec cash", "girocard", "kartenzahlung", "maestro", "visa", "mastercard", "kreditkarte"]
CASH_WORDS = ["bar", "gegeben"]
CHANGE_WORDS = ["rückgeld", "rueckgeld", "wechselgeld"]


def find_total(lines: list[str]) -> tuple[int | None, int | None]:
    """(index of the total line, total in cents)

    If the total line itself was not recognized, the payment lines still tell
    the total: a card payment is exactly the total, and with cash it is the
    money given minus the change.
    """
    total = _total_from_keywords(lines)
    if total[1] is None:
        total = _total_from_payment(lines)
    return total


def _total_from_payment(lines: list[str]) -> tuple[int | None, int | None]:
    for index, line in enumerate(lines):
        amount = _amount_at_end(line)
        if amount and amount > 0 and any(_sounds_like(line, w) or _has_word(line, [w]) for w in CARD_PAYMENT_WORDS):
            return index, amount
    given = change = None
    for index, line in enumerate(lines):
        amount = _amount_at_end(line)
        if amount is None:
            continue
        if given is None and _has_word(line, CASH_WORDS):
            given = (index, amount)
        elif change is None and any(_has_word(line, [w]) or _sounds_like(line, w) for w in CHANGE_WORDS):
            change = amount
    if given and change is not None and given[1] > change:
        return given[0], given[1] - change
    return None, None


def _total_from_keywords(lines: list[str]) -> tuple[int | None, int | None]:
    best = None
    for index, line in enumerate(lines):
        if _sounds_like(line, "zwischensumme") or _has_word(line, ["mwst", "netto", "steuer"]):
            continue
        for rank, word in enumerate(TOTAL_WORDS):
            if not (_has_word(line, [word]) or _sounds_like(line, word)):
                continue
            amount = _amount_at_end(line)
            # OCR sometimes puts the amount on the next line
            if amount is None and index + 1 < len(lines):
                amount = _amount_at_end(lines[index + 1])
            if amount is not None and amount > 0 and (best is None or rank < best[0]):
                best = (rank, index, amount)
            break
    return (best[1], best[2]) if best else (None, None)


def find_items(lines: list[str]) -> list[ReceiptItem]:
    items = []
    for line in lines:
        if QUANTITY.search(line) or _has_word(line, NOT_ITEM_WORDS) or DATE.search(line):
            continue
        match = LINE_AMOUNT.search(line)
        if not match:
            continue
        name = line[: match.start()].strip(" .:-*")
        if sum(c.isalpha() for c in name) < 2:
            continue
        items.append(ReceiptItem(_readable(name), _to_cents(match.group("amount"))))
    return items


def _readable(text: str) -> str:
    """Receipts print in capitals: "BIER 6ER" -> "Bier 6er" (mixed case stays as it is)."""
    if not text.isupper():
        return text
    return " ".join(word[:1] + word[1:].lower() if word[:1].isalpha() else word.lower() for word in text.split())


def _has_word(line: str, words: list[str]) -> bool:
    """Whole words only: "bar" (cash) must not hide "Barilla" or "Rhabarber"."""
    lowered = line.lower()
    return any(re.search(rf"(?<![a-zäöüß]){re.escape(w)}(?![a-zäöüß])", lowered) for w in words)


def _ocr_normalized(text: str) -> str:
    """Lower case with letters/digits OCR confuses mapped to one form, for comparing names.
    Umlauts are written out, because receipt printers often print "SUED" for "SÜD"."""
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return text.translate(str.maketrans("0158cav", "olsbeou"))


def _sounds_like(line: str, keyword: str) -> bool:
    """Keyword in the line even with broken spaces and one wrong letter ("S UMME", "SUMMC" ~ "summe")."""
    letters = re.sub(r"[^a-zäöüß]", "", line.lower())
    target = keyword.replace(" ", "")
    if target in letters:
        return True
    if len(target) < 5:
        return False
    size = len(target)
    windows = {letters[i:i + n] for n in (size - 1, size, size + 1) for i in range(len(letters) - n + 1)}
    return any(_within_one_edit(window, target) for window in windows)


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def _amount_at_end(line: str) -> int | None:
    match = LINE_AMOUNT.search(line)
    return _to_cents(match.group("amount")) if match else None


def _to_cents(amount: str) -> int:
    return round(float(amount.replace(",", ".")) * 100)
