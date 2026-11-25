"""Turn the text of a receipt photo (from OCR) into store, date, total and items.

The text recognition itself (Tesseract.js) runs on the phone, so the photo never
leaves it; only the recognized text comes here. OCR text is noisy: "0" becomes
"O", "1" becomes "l", spaces appear inside numbers. So every line is cleaned
first, then rules find the parts:

- store: a known shop name in the first lines (or printed again further down,
  "ALDI SÜD - Gutes für alle"), otherwise the first line with words
- date: the first plausible date (not in the future, not older than two years)
- total: the line with "zu zahlen", "Summe", "Gesamt", ... and an amount
  (an amount the payment lines confirm more often wins over a misread one)
- items: lines above the total and above the card-payment slip that end with
  an amount and maybe a tax code (skipping quantity lines like "2 Stk x 0,59",
  which belong to the line above, and the subtotal); article numbers in front
  of the names are removed; a price is checked against quantity × unit price
"""

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field

from billbuddy.data.generator import VARIABLE_COSTS

# A minus is a sign only after a space: in "Frischkäse ..4-2,09" it is a stray mark
AMOUNT = r"(?:(?<!\S)-)?\d{1,4}[.,]\d{2}"
# An amount at the end of a line, optionally followed by "€"/"EUR" and a tax code:
# letters (A, B, *; OCR also reads the "B" as "ß" or "8") or digits (drugstores:
# "2,45 1", garden centres "12.49 01"), plus marks OCR reads from the paper edge or
# the table ("2,35 | I", "4,60 ;", "3,79%")
TAIL_MARK = r"(?:\s+0?\d(?!\d)|8(?!\d)|\s*[A-Za-zß*]{1,2}(?![A-Za-zß])|\s*[|\[\]:;!.,'‘’\"_~%-]+)"
LINE_AMOUNT = re.compile(rf"(?P<amount>{AMOUNT})\s*(?:€|EUR)?{TAIL_MARK}{{0,3}}\s*$")
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
# Quantity and unit price: "3x 0,85 Fruchtgummi 2,55", "4 x 1,29", "2 * 7,49" (OCR: "2+7,49")
UNIT_PRICE = re.compile(rf"(?<![\w,.])(?P<count>\w?)\s?[xX×*+]\s?(?P<unit>{AMOUNT})(?!\d)")
# The count in front of a unit price: "4 x 1,29", "2 Stk x 0,59" (not "X 1,29" with a lost count)
QUANTITY_COUNT = re.compile(r"(?<![\d.,])(\d{1,3})\s*(?:stk\.?\s*)?[xX×*+]\s*\d", re.IGNORECASE)
# The price of the line above, worked out on its own line: "Preis: 3 x 4.99 = 14.97"
LINE_TOTAL = re.compile(rf"[xX×*+]\s*{AMOUNT}\s*=\s*(?P<total>{AMOUNT})")

# Total lines, best first ("Zwischensumme" is not the total)
TOTAL_WORDS = ["zu zahlen", "summe", "gesamtbetrag", "gesamt", "endbetrag", "total", "zahlbetrag", "betrag"]
# "Gesamtersparnis 1,00": what the discounts saved, neither the total nor an item
SAVINGS_WORDS = ["ersparnis", "gespart"]
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

CARD_PAYMENT_WORDS = [
    "ec-cash",
    "ec cash",
    "girocard",
    "kartenzahlung",
    "maestro",
    "visa",
    "mastercard",
    "kreditkarte",
    "amex",
    "american express",
]
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
    items = without_total_lines(items, total)
    if total is not None and sum(_amount_at_end(line) == total for line in lines) >= 2:
        # The total is printed twice (e.g. "Summe" and the card payment), so it is
        # reliable – and no single item can cost more than the whole receipt plus its discounts
        limit = total - sum(item.amount_cents for item in items if item.amount_cents < 0)
        items = [item for item in items if abs(item.amount_cents) <= limit]
    return Receipt(store=find_store(lines), date=find_date(lines, today), total_cents=total, items=items)


def without_total_lines(items: list[ReceiptItem], total: int | None) -> list[ReceiptItem]:
    """An "item" that costs exactly the total, next to other items, is the total or
    payment line read too badly to be recognized ("Kar tersahlung EUR 3,25")."""
    if total is None or sum(item.amount_cents > 0 for item in items) < 2:
        return items
    return [item for item in items if item.amount_cents != total]


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
    # Short names like "dm" are too risky for that, but their web address is clear
    # ("Öffnungszeiten auf dm.de")
    for line in footer:
        for store in [s for s in KNOWN_STORES if s not in GENERIC_SHOPS]:
            if re.search(rf"(?<![a-z0-9-]){re.escape(letters_only(store))}\.de\b", line.lower()):
                return store
    # A shop the app does not know, whose name is only a logo at the top, often
    # prints its web address below it ("Öffnungszeiten: gartenparadies.de")
    for line in header:
        domain = re.search(r"(?<![a-z0-9.-])([a-z]{3,})\.de\b", line.lower())
        if domain:
            return domain.group(1).capitalize()
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

    Candidates are the lines with a total keyword and the card-payment lines (a
    card payment is exactly the total). With cash and no total line, the total is
    the money given minus the change.
    """
    total = _total_from_lines(lines)
    if total[1] is None:
        total = _total_from_cash(lines)
    return total


def _total_from_cash(lines: list[str]) -> tuple[int | None, int | None]:
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


def _card_payments(lines: list[str]) -> dict[int, int]:
    """Lines of card payments with their amount: {index: cents}. Some shops print the
    payment as a minus ("KARTENZAHLUNG EUR -12,50"); it is the same amount."""
    payments = {}
    for index, line in enumerate(lines):
        amount = _amount_at_end(line)
        if amount and any(_sounds_like(line, w) or _has_word(line, [w]) for w in CARD_PAYMENT_WORDS):
            payments[index] = abs(amount)
    return payments


def _total_from_lines(lines: list[str]) -> tuple[int | None, int | None]:
    """Which candidate is the total:
    1. the amount printed most often: "Summe 812,50" (a mark read as "8") loses
       against "Betrag 12,50" and "girocard 12,50"
    2. an amount not below the items found so far: "Summe 2,20" (a lost "7") is
       impossible when the items already add up to 7,20
    3. the best keyword ("zu zahlen" before "Summe" ... before the card payment)"""
    candidates = []  # (rank, index, amount)
    for index, line in enumerate(lines):
        if _is_subtotal(line) or _is_savings(line) or _has_word(line, ["mwst", "netto", "steuer"]):
            continue
        for rank, word in enumerate(TOTAL_WORDS):
            if not (_has_word(line, [word]) or _sounds_like(line, word)):
                continue
            amount = _amount_at_end(line)
            # OCR sometimes puts the amount on the next line
            if amount is None and index + 1 < len(lines):
                amount = _amount_at_end(lines[index + 1])
            if amount is not None and amount > 0:
                candidates.append((rank, index, amount))
            break
    payments = _card_payments(lines)
    candidates += [(len(TOTAL_WORDS), index, amount) for index, amount in payments.items()]
    if not candidates:
        return None, None
    confirmations = Counter(({index: amount for _, index, amount in candidates} | payments).values())
    items = find_items(lines[: items_end(lines, min(index for _, index, _ in candidates))])
    items_sum = sum(item.amount_cents for item in items)
    _, index, amount = max(candidates, key=lambda c: (confirmations[c[2]], c[2] >= items_sum - 1, -c[0], -c[1]))
    return index, amount


def items_end(lines: list[str], total_index: int | None) -> int:
    """Index of the first line after the items: the total or the card-payment slip."""
    end = len(lines) if total_index is None else total_index
    for index, line in enumerate(lines[:end]):
        if any(_sounds_like(line, w) for w in PAYMENT_SLIP_WORDS) or _has_word(line, CARD_PAYMENT_WORDS):
            return index
    return end


def find_items(lines: list[str]) -> list[ReceiptItem]:
    items = []
    quantity_side = _quantity_side(lines)
    name_above = None  # a line with only a name: the price may follow on the next line
    last_item_line = None
    for index, line in enumerate(lines):
        # "Preis: 3 x 4.99 = 14.97" right below an item is that item's real price
        line_total = LINE_TOTAL.search(line)
        if line_total and last_item_line == index - 1:
            items[-1].amount_cents = _to_cents(line_total.group("total"))
            continue
        if _is_quantity_line(line):
            # "2 x 7,49   14,98" below "Gartenstuhl": quantity and price of the name above
            price = _price_after_unit_price(line)
            if price is not None and name_above:
                items.append(ReceiptItem(name_above, price))
                last_item_line = index
            name_above = None
            continue
        if _has_word(line, NOT_ITEM_WORDS) or _is_subtotal(line) or _is_savings(line) or DATE.search(line):
            name_above = None
            continue
        if _sounds_like(line, "aldi preis"):  # Aldi's total line
            name_above = None
            continue
        match = LINE_AMOUNT.search(line)
        if not match:
            name_above = _name_only(line)
            continue
        name = _clean_name(line[: match.start()])
        if sum(c.isalpha() for c in name) < 2:
            # The price is on the line below the name, or the name was not readable:
            # the amount still counts, and the user can type the name in the form
            name = name_above or "?"
        texts = [line[: match.start()]] + _quantity_lines_for(lines, index, quantity_side)
        items.append(ReceiptItem(_readable(name), _checked_by_unit_price(texts, _to_cents(match.group("amount")))))
        last_item_line = index
        name_above = None
    return items


def _clean_name(text: str) -> str:
    # Marks OCR reads from the paper edge or dirt: "Spaghetti 500g]", "Pfand °"
    return ARTICLE_NUMBER.sub("", text).strip(" .,:;-*=_—»«„“\"'‘’`´°|[]")


def _name_only(line: str) -> str | None:
    """A line that is only a product name ("Gartenstuhl"), not marks or numbers."""
    name = _clean_name(line)
    letters = sum(c.isalpha() for c in name)
    return _readable(name) if letters >= 3 and letters >= len(name.replace(" ", "")) / 2 else None


def _price_after_unit_price(line: str) -> int | None:
    """ "2 x 7,49   14,98 A" -> 1498; None for "2 Stk x 0,59" (only the unit price)."""
    unit = UNIT_PRICE.search(line)
    price = LINE_AMOUNT.search(line)
    if unit and price and unit.end() <= price.start():
        return _to_cents(price.group("amount"))
    return None


def _quantity_side(lines: list[str]) -> int | None:
    """Where the quantity line ("4 x 1,29") stands: -1 above its item (discounters),
    +1 below it (supermarkets), None if unclear. Learned from this receipt: the
    quantity lines whose count x unit price is exactly the price next to them."""
    votes = Counter()
    for index, line in enumerate(lines):
        count, unit = QUANTITY_COUNT.search(line), UNIT_PRICE.search(line)
        if not (_is_quantity_line(line) and count and unit):
            continue
        product = int(count.group(1)) * _to_cents(unit.group("unit"))
        for item_index, side in ((index + 1, -1), (index - 1, 1)):
            neighbour = lines[item_index] if 0 <= item_index < len(lines) else ""
            if not _is_quantity_line(neighbour) and _amount_at_end(neighbour) == product:
                votes[side] += 1
    ranked = votes.most_common()
    if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def _quantity_lines_for(lines: list[str], index: int, side: int | None) -> list[str]:
    """The quantity line next to an item. If the receipt does not tell on which side
    they stand, both neighbours are tried – but not a quantity line whose count x unit
    price already fits the line on its other side: it belongs to that line."""
    found = []
    for quantity in [index + side] if side else [index - 1, index + 1]:
        if not (0 <= quantity < len(lines) and _is_quantity_line(lines[quantity])):
            continue
        other = 2 * quantity - index  # the line on the other side of the quantity line
        if side is None and 0 <= other < len(lines) and _is_multiple_of_unit(lines[quantity], lines[other]):
            continue
        found.append(lines[quantity])
    return found


def _is_multiple_of_unit(quantity_line: str, line: str) -> bool:
    unit, cents = UNIT_PRICE.search(quantity_line), _amount_at_end(line)
    return bool(unit and cents and cents > 0 and cents % _to_cents(unit.group("unit")) == 0)


def _checked_by_unit_price(texts: list[str], cents: int) -> int:
    """ "3x 0,85 Fruchtgummi 2,59": 3 × 0,85 is 2,55, so one digit of the price was
    misread (5 and 9 look alike on receipts). The quantity and unit price may also be
    on their own line next to the item ("4 x 1,29"). Corrected only when the price
    differs from a multiple of the unit price in exactly one digit."""
    for text in texts:
        unit_match = UNIT_PRICE.search(text)
        unit = _to_cents(unit_match.group("unit")) if unit_match else 0
        if unit <= 0 or cents <= 0:
            continue
        count = QUANTITY_COUNT.search(text)
        # The printed count first; if that was misread too, the nearest multiple
        for times in ([int(count.group(1))] if count else []) + [round(cents / unit)]:
            expected = times * unit
            if expected == cents:
                return cents
            printed, wanted = str(cents), str(expected)
            differ = len(printed) == len(wanted) and sum(a != b for a, b in zip(printed, wanted, strict=True)) == 1
            if times >= 2 and differ:
                return expected
    return cents


def _is_savings(line: str) -> bool:
    return _sounds_like(line, "ersparnis") or _has_word(line, ["gespart"])


def _is_subtotal(line: str) -> bool:
    """ "Zwischensumme 4,60": the items above added up, no item itself (discounts may follow)."""
    return _sounds_like(line, "zwischensumme")


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
