"""Tests for the receipt parser in billbuddy.ml.receipt_ocr."""

import datetime as dt

import pytest

from billbuddy.ml.receipt_ocr.parser import clean_line, parse_receipt

TODAY = dt.date(2026, 10, 29)

REWE = """
REWE Markt GmbH
Musterstraße 12
90402 Nürnberg
                     EUR
BIO BANANEN          1,99 B
VOLLMILCH 3,5%       1,15 B
BRÖTCHEN             1,18 B
   2 Stk x  0,59
BARILLA SPAGHETTI    1,79 B
PFAND 0,25           0,25 A
--------------------------
SUMME           EUR  6,36
==========================
Geg. EC-Cash    EUR  6,36
MwSt  7%  Netto 5,71  MwSt 0,40
Datum: 28.10.2026  Uhrzeit: 18:45
"""

LIDL = """
LIDL
Lidl sagt Danke
Bananen          1,29 A
Rhabarber        2,49 A
Gouda jung       2,19 A
Rabatt          -0,50 A
zu zahlen        5,47
Bar             10,00
Rückgeld         4,53
27.10.26 09:12
"""


def test_rewe_receipt():
    receipt = parse_receipt(REWE, TODAY)
    assert receipt.store == "Rewe"
    assert receipt.date == dt.date(2026, 10, 28)
    assert receipt.total_cents == 636
    assert [(i.name, i.amount_cents) for i in receipt.items] == [
        ("Bio Bananen", 199),
        ("Vollmilch 3,5%", 115),
        ("Brötchen", 118),
        ("Barilla Spaghetti", 179),
        ("Pfand 0,25", 25),
    ]
    assert receipt.items_match_total


def test_lidl_receipt_with_discount_and_cash():
    receipt = parse_receipt(LIDL, TODAY)
    assert receipt.store == "Lidl"
    assert receipt.date == dt.date(2026, 10, 27)
    assert receipt.total_cents == 547  # not the 10,00 given in cash
    assert [i.name for i in receipt.items] == ["Bananen", "Rhabarber", "Gouda jung", "Rabatt"]
    assert receipt.items[-1].amount_cents == -50
    assert receipt.items_match_total


def test_ocr_noise_in_numbers_is_repaired():
    # Typical OCR mistakes: "1" read as "l", "0" read as "O", a space inside the number
    noisy = REWE.replace("1,99", "l,99").replace("0,25 A", "O,25 A").replace("1,18", "1, 18")
    receipt = parse_receipt(noisy, TODAY)
    assert [i.amount_cents for i in receipt.items] == [199, 115, 118, 179, 25]
    assert receipt.total_cents == 636
    assert receipt.items_match_total


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("BANANEN   l,99 B", "BANANEN 1,99 B"),
        ("Summe 2O,5O", "Summe 20,50"),
        ("Brot 1, 29", "Brot 1,29"),
        ("BIO HAFERDRINK 1,49", "BIO HAFERDRINK 1,49"),  # letters in words stay letters
    ],
)
def test_clean_line(raw, cleaned):
    assert clean_line(raw) == cleaned


def test_capital_letters_become_readable():
    receipt = parse_receipt("REWE\nBIER 6ER 5,49 A\nBIO HAFERDRINK 1,49 B\nSumme 6,98", TODAY)
    assert [i.name for i in receipt.items] == ["Bier 6er", "Bio Haferdrink"]


def test_unknown_store_uses_the_first_line_with_words():
    receipt = parse_receipt("BÄCKEREI MÜLLER\nBrezel 0,90\nGesamt 0,90", TODAY)
    assert receipt.store == "Bäckerei Müller"
    assert receipt.total_cents == 90


def test_total_on_the_next_line():
    receipt = parse_receipt("dm\nZahnpasta 1,95\nSUMME\n1,95", TODAY)
    assert receipt.total_cents == 195


def test_implausible_dates_are_ignored():
    receipt = parse_receipt("Rewe\n31.02.2026\n01.01.2019\n15.10.2026\nSumme 1,00", TODAY)
    assert receipt.date == dt.date(2026, 10, 15)


def test_empty_or_unreadable_text():
    receipt = parse_receipt("~~ ### ~~", TODAY)
    assert (receipt.store, receipt.date, receipt.total_cents, receipt.items) == (None, None, None, [])
    assert not receipt.items_match_total


@pytest.mark.parametrize("label", ["S UMME", "SUMMC", "Su mme", "ZU ZAHLFN"])
def test_total_keyword_survives_ocr_noise(label):
    receipt = parse_receipt(f"Rewe\nBrot 1,29\n{label} 1,29\nBar 5,00", TODAY)
    assert receipt.total_cents == 129


def test_zwischensumme_is_not_the_total():
    receipt = parse_receipt("Rewe\nBrot 1,29\nZwischensumme 1,29\nKäse 2,00\nSumme 3,29", TODAY)
    assert receipt.total_cents == 329


def test_date_with_confused_digits():
    receipt = parse_receipt("Rewe\nSumme 1,00\nDatum: 28.1O.2O26", TODAY)
    assert receipt.date == dt.date(2026, 10, 28)


def test_store_with_confused_characters():
    assert parse_receipt("R0SSMANN\nSumme 1,00", TODAY).store == "Rossmann"


# --- API ---


def test_api_parses_a_receipt(client, monkeypatch):
    from billbuddy.api import receipt_routes

    monkeypatch.setattr(receipt_routes, "today", lambda: TODAY)
    group = client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()

    body = client.post(f"/api/groups/{group['id']}/parse-receipt", json={"text": REWE}).json()

    assert (body["store"], body["date"], body["total"]) == ("Rewe", "2026-10-28", 6.36)
    assert [i["amount"] for i in body["items"]] == [1.99, 1.15, 1.18, 1.79, 0.25]
    assert body["items_match_total"]
    assert body["category"] == "Groceries"


def test_api_needs_access_to_the_group(client, anon_client):
    assert client.post("/api/groups/999/parse-receipt", json={"text": REWE}).status_code == 404
    client.post("/api/auth/logout")
    assert anon_client.post("/api/groups/1/parse-receipt", json={"text": REWE}).status_code == 401
