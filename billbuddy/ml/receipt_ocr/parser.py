"""Turn the text of a receipt photo (from OCR) into store, date, total and items.

The text recognition itself (Tesseract.js) runs on the phone, so the photo never
leaves it; only the recognized text comes here. OCR text is noisy: "0" becomes
"O", "1" becomes "l", spaces appear inside numbers. So every line is cleaned
first, then rules find the parts:

- store: a known shop name in the first lines (or printed again further down,
  "ALDI SÜD - Gutes für alle"), otherwise the first line with words
- date: the first plausible date (not in the future, not older than two years)
- total: the line with "zu zahlen", "Summe", "Gesamt", ... and an amount
- items: lines above the total and above the card-payment slip that end with
  an amount (skipping quantity lines like "2 Stk x 0,59", which belong to the
  line above); article numbers in front of the names are removed
"""

import datetime as dt
import re
from dataclasses import dataclass, field

from billbuddy.data.generator import VARIABLE_COSTS

AMOUNT = r"-?\d{1,4}[.,]\d{2}"
# An amount at the end of a line, optionally followed by "€"/"EUR" and a tax code
# (A, B, *; OCR also reads the "B" as "ß" or "8")
LINE_AMOUNT = re.compile(rf"(?P<amount>{AMOUNT})\s*(?:€|EUR)?[\s.]*(?:[A-Za-zß*]{{1,2}}|8)?\s*$")
DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
# Date-shaped text with letters OCR confuses with digits ("28.1O.2O26")
DATE_LIKE = re.compile(r"(?<![A-Za-z])[\dOoQlIiSB]{1,2}[./-][\dOoQlIiSB]{1,2}[./-][\dOoQlIiSB]{2,4}(?![A-Za-z])")
DIGIT_FIXES = str.maketrans("OoQlIiSB", "00011158")
# Lines that only explain the line above: "2 Stk x 0,59", "0,846 kg x 1,99 EUR/kg"
QUANTITY = re.compile(r"^\s*\d+([.,]\d+)?\s*(x|stk|st\b|kg)|\bx\s*\d+[.,]\d{2}\b|eur\s*/\s*kg", re.IGNORECASE)
QUANTITY_UNITS = re.compile(r"stk|st|eur|kg|x", re.IGNORECASE)
# Discounters print an article number in front of the name ("123456 Mineralwasser");
# OCR sometimes reads stray characters from the paper edge before it ("Es 345678 Joghurt")
ARTICLE_NUMBER = re.compile(r"^(?:.*?\s)?\d{5,8}\s+")

# Total lines, best first ("Zwischensumme" is not the total)
TOTAL_WORDS = ["zu zahlen", "summe", "gesamtbetrag", "gesamt", "endbetrag", "total", "zahlbetrag", "betrag"]
TAX_WORDS = ["mwst", "ust", "netto", "brutto", "steuer"]
# Lines below the items that are no items
NOT_ITEM_WORDS = [
    "summe",
    "gesamt",
    "zu zahlen",
    "total",
    "betrag",
    "mwst",
    "ust",
    "netto",
    "brutto",
    "steuer",
    "gegeben",
    "rückgeld",
    "rueckgeld",
    "wechselgeld",
    "bar",
    "ec-cash",
    "girocard",
    "kartenzahlung",
    "visa",
    "mastercard",
    "zahlung",
    "datum",
    "uhrzeit",
    "kasse",
    "bon-nr",
    "beleg",
]

CARD_PAYMENT_WORDS = ["ec-cash", "ec cash", "girocard", "kartenzahlung", "maestro", "visa", "mastercard", "kreditkarte"]
CASH_WORDS = ["bar", "gegeben"]
CHANGE_WORDS = ["rückgeld", "rueckgeld", "wechselgeld"]
# Some shops print the card-payment slip between the items and the total
# ("K-U-N-D-E-N-B-E-L-E-G ... Kartenzahlung ... Betrag"); no items come after it
PAYMENT_SLIP_WORDS = ["kundenbeleg", "kartenzahlung", "zahlung erfolgt"]

KNOWN_STORES = sorted(
    {merchant for _, _, _, merchants in VARIABLE_COSTS.values() for merchant in merchants},
    key=len,
    reverse=True,  # "Aldi Süd" before "Aldi"
)
# Kinds of shops, not brands: "BÄCKEREI MÜLLER" should stay "Bäckerei Müller"
GENERIC_SHOPS = {
    "Bäckerei",
    "Metzgerei",
    "Wochenmarkt",
    "Pizzeria",
    "Café",
    "Döner",
    "Sushi Bar",
    "Biergarten",
    "Kino",
    "Konzert",
    "Bowling",
    "Schwimmbad",
    "Museum",
    "Kletterhalle",
    "Apotheke",
    "Optiker",
    "Zahnarzt",
    "Physiotherapie",
    "Hotel",
    "Ferienwohnung",
    "Geschenk",
    "Post",
    "Friseur",
    "Spende",
    "Blumen",
    "Parkhaus",
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
    items = find_items(lines[: items_end(lines, total_index)])
    if total is not None and sum(_amount_at_end(line) == total for line in lines) >= 2:
        # The total is printed twice (e.g. "Summe" and the card payment), so it is
        # reliable – and no single item can cost more than the whole receipt
        items = [item for item in items if abs(item.amount_cents) <= total]
    return Receipt(store=find_store(lines), date=find_date(lines, today), total_cents=total, items=items)


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
    line = " ".join(line.split())
    # Decimal separators read as other marks: "1'49" -> "1,49"; "1:09 A" -> "1,09 A"
    # (a colon only before a tax code, so times like "19:24" stay times)
    line = re.sub(r"(\d)['’‘´`](\d{2})(?!\d)", r"\1,\2", line)
    line = re.sub(r"(\d):(\d{2}) ([AB])$", r"\1,\2 \3", line)
    # Lost decimal separator in front of a tax code: "Schokolade 119 A" -> "1,19 A"
    return re.sub(r"(?<![\d.,])(\d)(\d{2}) ([AB])$", r"\1,\2 \3", line)


def find_store(lines: list[str]) -> str | None:
    header = lines[:8]
    for fuzzy in (False, True):
        for line in header:
            store = _known_store(line, KNOWN_STORES, fuzzy)
            if store:
                return _readable(line) if store in GENERIC_SHOPS and not _amount_at_end(line) else store
    # The name at the top may be unreadable, but many shops print it again further
    # down ("ALDI SÜD - Gutes für alle"). Only brands with longer names here: short
    # words like "Netto" also appear in the tax lines.
    footer = [line for line in lines[8:] if _amount_at_end(line) is None and not _has_word(line, TAX_WORDS)]
    brands = [s for s in KNOWN_STORES if s not in GENERIC_SHOPS and len(letters_only(ocr_normalized(s))) >= 5]
    for fuzzy in (False, True):
        for line in footer:
            store = _known_store(line, brands, fuzzy)
            if store:
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


def _known_store(line: str, stores: list[str], fuzzy: bool) -> str | None:
    """A store name in the line; fuzzy allows one wrong letter ("ALDI SOD"), only for
    names with at least 7 letters, because short names would match ordinary words."""
    normalized = ocr_normalized(line)
    for store in stores:
        name = ocr_normalized(store)
        if fuzzy:
            if len(letters_only(name)) >= 7 and _sounds_like(normalized, name):
                return store
        elif re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", normalized):
            return store
    return None


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


def items_end(lines: list[str], total_index: int | None) -> int:
    """Index of the first line after the items: the total or the card-payment slip."""
    end = len(lines) if total_index is None else total_index
    for index, line in enumerate(lines[:end]):
        if any(_sounds_like(line, w) for w in PAYMENT_SLIP_WORDS) or _has_word(line, CARD_PAYMENT_WORDS):
            return index
    return end


def find_items(lines: list[str]) -> list[ReceiptItem]:
    items = []
    for line in lines:
        if _is_quantity_line(line) or _has_word(line, NOT_ITEM_WORDS) or DATE.search(line):
            continue
        match = LINE_AMOUNT.search(line)
        if not match:
            continue
        # Marks OCR reads from the paper edge or dirt: "Spaghetti 500g]", "Pfand °"
        name = ARTICLE_NUMBER.sub("", line[: match.start()]).strip(" .,:;-*=_—»«„“\"'‘’`´°|[]")
        if sum(c.isalpha() for c in name) < 2:
            continue
        items.append(ReceiptItem(_readable(name), _to_cents(match.group("amount"))))
    return items


def _is_quantity_line(line: str) -> bool:
    """ "2 Stk x 0,59" explains the line above; "6x Mineralwasser 6x1,5l 2,94" is an item itself."""
    if not QUANTITY.search(line):
        return False
    # Only units are left once numbers are removed ("Stkx" when OCR lost the spaces)
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", line)
    return all(not QUANTITY_UNITS.sub("", word) for word in words)


def _readable(text: str) -> str:
    """Receipts print in capitals: "BIER 6ER" -> "Bier 6er" (mixed case stays as it is)."""
    if not text.isupper():
        return text
    return " ".join(word[:1] + word[1:].lower() if word[:1].isalpha() else word.lower() for word in text.split())


def _has_word(line: str, words: list[str]) -> bool:
    """Whole words only: "bar" (cash) must not hide "Barilla" or "Rhabarber"."""
    lowered = line.lower()
    return any(re.search(rf"(?<![a-zäöüß]){re.escape(w)}(?![a-zäöüß])", lowered) for w in words)


def ocr_normalized(text: str) -> str:
    """Lower case with letters/digits OCR confuses mapped to one form, for comparing names.
    "SÜD", "SUED" (printers without umlauts) and "SUD" (OCR lost the dots) become the same."""
    text = text.lower()
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ae", "a"), ("oe", "o"), ("ue", "u"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    return text.translate(str.maketrans("0158cav", "olsbeou"))


def letters_only(text: str) -> str:
    return re.sub(r"[^a-zäöüß]", "", text.lower())


def _sounds_like(line: str, keyword: str) -> bool:
    """Keyword in the line even with broken spaces and one wrong letter ("S UMME", "SUMMC" ~ "summe")."""
    letters = letters_only(line)
    target = letters_only(keyword)
    if target in letters:
        return True
    if len(target) < 5:
        return False
    size = len(target)
    windows = {letters[i : i + n] for n in (size - 1, size, size + 1) for i in range(len(letters) - n + 1)}
    return any(_within_one_edit(window, target) for window in windows)


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def _amount_at_end(line: str) -> int | None:
    match = LINE_AMOUNT.search(line)
    return _to_cents(match.group("amount")) if match else None


def _to_cents(amount: str) -> int:
    return round(float(amount.replace(",", ".")) * 100)
