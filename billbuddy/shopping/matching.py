"""Which shopping-list entries were bought, according to a scanned receipt.

People write "Milch" on the list, the receipt says "Vollmilch 3,5% 1l". Rules:

- The entry's main word is its last word ("frische Milch" -> "milch").
- German compounds have their main part at the end: "Vollmilch" is milk,
  "Milchschokolade" is chocolate. So an entry matches a receipt word that ends
  with it, if at least three letters come before it ("Eis" must not match "Reis").
- Plural endings are ignored ("Tomaten" ~ "Tomate"), umlauts may be missing
  ("AEPFEL" ~ "Äpfel"), and longer words may have one wrong letter (OCR).

Synonyms ("Klopapier" ~ "Toilettenpapier") are not recognized.
"""

import re
from dataclasses import dataclass

# Plural and inflection endings, longest first
ENDINGS = ("en", "er", "n", "e", "s")
MIN_COMPOUND_PREFIX = 3
MIN_FUZZY_LENGTH = 5


@dataclass
class Match:
    entry_id: int
    entry: str
    receipt_item: str


def bought_entries(entries: list[tuple[int, str]], receipt_items: list[str]) -> list[Match]:
    """entries: (id, name) of the shopping list; receipt_items: the item names on the receipt.
    Every entry that one of the receipt items matches, with the first such item."""
    receipt_words = [(name, [_stem(w) for w in _words(name)]) for name in receipt_items]
    matches = []
    for entry_id, entry in entries:
        words = _words(entry)
        if not words:
            continue
        head = _stem(words[-1])
        item = next((name for name, stems in receipt_words if any(_ends_with(s, head) for s in stems)), None)
        if item is not None:
            matches.append(Match(entry_id, entry, item))
    return matches


def _words(text: str) -> list[str]:
    text = text.lower()
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss"), ("ae", "a"), ("oe", "o"), ("ue", "u")):
        text = text.replace(umlaut, plain)
    return re.findall(r"[a-z]{3,}", text)


def _stem(word: str) -> str:
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def _ends_with(word: str, head: str) -> bool:
    """The word is the head itself, or a compound ending with it ("vollmilch")."""
    if word == head:
        return True
    if len(word) - len(head) >= MIN_COMPOUND_PREFIX and word.endswith(head):
        return True
    if len(head) < MIN_FUZZY_LENGTH:
        return False
    # One OCR mistake: compare the end of the word, allowing one letter more or less
    return any(
        _within_one_edit(word[-n:], head) and (len(word) == n or len(word) - n >= MIN_COMPOUND_PREFIX)
        for n in (len(head) - 1, len(head), len(head) + 1)
        if 0 < n <= len(word)
    )


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))
