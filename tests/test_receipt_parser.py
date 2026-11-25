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

# Discounter layout (invented content): article numbers in front of the names, tax
# codes misread by OCR, and the card-payment slip printed *between* items and total
DISCOUNTER = """
ALDI SÜD
Musterstraße 1
12345 Musterstadt
                                 EUR
Eigenmarke: Pfand             -0,25 B
6x 123456 Mineralwasser 6x1,5l 2,94 B
6 x 0,25
80000123 Pfand                 1,50 ß
234567 Kartoffeln festk.       2,49 A
Es 345678 Joghurt 500g         1:09 A
456789 Schokolade Vollmilch    119 A
567890 Äpfel                   1,62 A
0,810 kg x 1,99 EUR/kg
K-U-N-D-E-N-B-E-L-E-G
ALDI SÜD 001-002
Kartenzahlung girocard
Betrag                    10,58 EUR
28.10.2026   18:12   T-ID 11111111
VU-Nummer                1234567890
** Zahlung erfolgt **
S u m m e                     10,58
7 Artikel
girocard          EUR         10,58
A 07,0% Netto 6,15 MwSt 0,43
B 19,0% Netto 3,36 MwSt 0,64
Mo - Sa: 7:00 Uhr - 20:00 Uhr
"""

# Drugstore layout: tax rate as a digit behind the price, quantity in front of the
# name, a subtotal with a discount below it
DRUGSTORE = """
dm drogerie markt
Musterweg 3
12345 Musterstadt
28.10.2026 17:45 ABCD/1 123456/2 1234
Spülmittel Zitrone              1,45 1
Zahnbürste mittel               2,75 1
3x 0,85 Fruchtgummi Bären       2,55 2
Kaugummi Minze 10St             1,20 2
Zwischensumme                   7,95
dm-Rabatte auf rabattfähige Artikel
Sonderartikelrabatt 30 %       -0,36
SUMME EUR                       7,59
KARTENZAHLUNG EUR              -7,59
MwSt-Satz   Brutto   Netto   MwSt
1=19,00%      4,20    3,53   0,67
2=7,00%       3,39    3,17   0,22
Öffnungszeiten auf dm.de
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
        ("Joghurt 500g 1:09 A", "Joghurt 500g 1,09 A"),
        ("Tortilla Wraps 1'79 A", "Tortilla Wraps 1,79 A"),
        ("Schokolade 119 A", "Schokolade 1,19 A"),  # lost decimal comma before the tax code
        ("29.10.2026 19:24", "29.10.2026 19:24"),  # times stay times
        ("Mo - Sa: 7:00 Uhr - 20:00 Uhr", "Mo - Sa: 7:00 Uhr - 20:00 Uhr"),
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


def test_total_from_card_payment_when_the_total_line_is_lost():
    text = "REWE\nBIO BANANEN 1,99 B\nSHAMPOO 2,95 A\nGeg. EC-Cash 4,94\nDatum: 28.10.2026"
    receipt = parse_receipt(text, TODAY)
    assert receipt.total_cents == 494
    assert [i.amount_cents for i in receipt.items] == [199, 295]


def test_total_from_cash_minus_change_when_the_total_line_is_lost():
    receipt = parse_receipt("LIDL\nBananen 1,29 A\nGouda 2,19 A\nBar 10,00\nRückgeld 6,52", TODAY)
    assert receipt.total_cents == 348
    assert receipt.items_match_total


def test_zwischensumme_is_not_the_total():
    receipt = parse_receipt("Rewe\nBrot 1,29\nZwischensumme 1,29\nKäse 2,00\nSumme 3,29", TODAY)
    assert receipt.total_cents == 329


def test_date_with_confused_digits():
    receipt = parse_receipt("Rewe\nSumme 1,00\nDatum: 28.1O.2O26", TODAY)
    assert receipt.date == dt.date(2026, 10, 28)


def test_store_printed_without_umlauts():
    assert parse_receipt("ALDI SUED\nSumme 1,00", TODAY).store == "Aldi Süd"
    assert parse_receipt("ALDI SUD\nSumme 1,00", TODAY).store == "Aldi Süd"  # OCR lost the dots


def test_store_with_one_wrong_letter():
    assert parse_receipt("ALDI SOD\nSumme 1,00", TODAY).store == "Aldi Süd"


def test_store_printed_again_at_the_bottom():
    items = "\n".join(f"Artikel {n} 1,00 A" for n in range(9))
    text = f"~~ ### ~~\n{items}\nSumme 9,00\nB 19% Netto 7,56 MwSt 1,44 x\nALDI SÜD - Gutes für alle."
    assert parse_receipt(text, TODAY).store == "Aldi Süd"


def test_tax_line_at_the_bottom_is_not_the_store_netto():
    items = "\n".join(f"Artikel {n} 1,00 A" for n in range(9))
    receipt = parse_receipt(f"~~ ### ~~\n{items}\nSumme 9,00\nB 19% Netto 7,56 MwSt 1,44 x", TODAY)
    assert receipt.store != "Netto"


def test_discounter_receipt_with_card_slip_before_the_total():
    receipt = parse_receipt(DISCOUNTER, TODAY)
    assert receipt.store == "Aldi Süd"
    assert receipt.date == dt.date(2026, 10, 28)
    assert receipt.total_cents == 1058
    assert [(i.name, i.amount_cents) for i in receipt.items] == [
        ("Eigenmarke: Pfand", -25),
        ("Mineralwasser 6x1,5l", 294),
        ("Pfand", 150),
        ("Kartoffeln festk", 249),
        ("Joghurt 500g", 109),
        ("Schokolade Vollmilch", 119),
        ("Äpfel", 162),
    ]
    assert receipt.items_match_total


def test_quantity_lines_are_skipped_but_items_with_a_quantity_kept():
    receipt = parse_receipt("Rewe\n2 x Milch 1,98 A\n2Stkx0,99\n0,5 kg x 2,00 EUR/kg\nSumme 1,98", TODAY)
    assert [(i.name, i.amount_cents) for i in receipt.items] == [("2 x Milch", 198)]


def test_item_dearer_than_a_confirmed_total_is_dropped():
    # The total is printed twice (Summe + card payment), so "451,20" must be misread
    text = "Rewe\nBrot 1,29 A\nKontaktlos 451,20\nKäse 2,00 A\nSumme 3,29\nGeg. EC-Cash 3,29"
    receipt = parse_receipt(text, TODAY)
    assert [i.amount_cents for i in receipt.items] == [129, 200]


def test_item_dearer_than_the_total_is_kept_when_a_discount_explains_it():
    text = "dm\nKaffee 7,52 2\nRabatt 30 % -2,26\nSUMME EUR 5,26\nGeg. EC-Cash EUR 5,26"
    receipt = parse_receipt(text, TODAY)
    assert [i.amount_cents for i in receipt.items] == [752, -226]
    assert receipt.items_match_total


def test_items_are_kept_when_the_total_is_printed_only_once():
    # "zu zahlen 2 0,97" was read as 0,97: the items must not be thrown away because of it
    receipt = parse_receipt("Rossmann\nShampoo 4,48 A\nDuschgel 1,60 B\nzu zahlen 2 0,97", TODAY)
    assert [i.amount_cents for i in receipt.items] == [448, 160]


def test_store_with_confused_characters():
    assert parse_receipt("R0SSMANN\nSumme 1,00", TODAY).store == "Rossmann"


def test_drugstore_receipt_with_tax_digits_and_subtotal():
    receipt = parse_receipt(DRUGSTORE, TODAY)
    assert receipt.store == "dm"
    assert receipt.date == dt.date(2026, 10, 28)
    assert receipt.total_cents == 759
    assert [(i.name, i.amount_cents) for i in receipt.items] == [
        ("Spülmittel Zitrone", 145),
        ("Zahnbürste mittel", 275),
        ("3x 0,85 Fruchtgummi Bären", 255),
        ("Kaugummi Minze 10St", 120),
        ("Sonderartikelrabatt 30 %", -36),
    ]
    assert receipt.items_match_total


@pytest.mark.parametrize("ending", ["2,35 | I", "2,35 ;", "2,35 2 I", "2,35 ]", "2,35 €"])
def test_marks_behind_the_price_are_ignored(ending):
    # OCR reads the paper edge or the table next to the receipt as extra marks
    receipt = parse_receipt(f"Rewe\nDuschgel {ending}\nSumme 2,35", TODAY)
    assert [i.amount_cents for i in receipt.items] == [235]


def test_words_and_weights_behind_a_number_are_no_price():
    text = "Rewe\n3x 0,85 Gummibärchen\nÄpfel lose 0,810\nBrot 2,00 A\nSumme 2,00"
    assert [i.name for i in parse_receipt(text, TODAY).items] == ["Brot"]


def test_price_checked_against_quantity_times_unit_price():
    # 3 x 0,85 is 2,55: "2,59" has one misread digit; "4,99" is too far off to correct
    receipt = parse_receipt("Rewe\n3x 0,85 Fruchtgummi 2,59 2\n3x 0,85 Lakritz 4,99 2\nSumme 7,54", TODAY)
    assert [i.amount_cents for i in receipt.items] == [255, 499]


def test_total_confirmed_by_the_payment_lines_wins():
    # "Summe" was misread (a mark in front read as "8"); card slip and payment line agree
    text = "Aldi Süd\nBrot 2,10 A\nBetrag 12,50 EUR\nSumme 812,50\ngirocard EUR 12,50"
    assert parse_receipt(text, TODAY).total_cents == 1250


def test_store_from_its_web_address_at_the_bottom():
    receipt = parse_receipt(DRUGSTORE.replace("dm drogerie markt", "~~ ### ~~"), TODAY)
    assert receipt.store == "dm"


# --- API ---


def test_api_parses_a_receipt(client, monkeypatch):
    # A single "text" is what app versions before 30 Oct 2026 send
    from billbuddy.api import receipt_routes

    monkeypatch.setattr(receipt_routes, "today", lambda: TODAY)
    group = client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()

    body = client.post(f"/api/groups/{group['id']}/parse-receipt", json={"text": REWE}).json()

    assert (body["store"], body["date"], body["total"]) == ("Rewe", "2026-10-28", 6.36)
    assert [i["amount"] for i in body["items"]] == [1.99, 1.15, 1.18, 1.79, 0.25]
    assert body["items_match_total"]
    assert body["category"] == "Groceries"


def test_api_combines_several_readings(client, monkeypatch):
    from billbuddy.api import receipt_routes

    monkeypatch.setattr(receipt_routes, "today", lambda: TODAY)
    group = client.post("/api/groups", json={"name": "Home", "members": ["Ben"]}).json()
    incomplete = REWE.replace("BARILLA SPAGHETTI    1,79 B\n", "")

    body = client.post(f"/api/groups/{group['id']}/parse-receipt", json={"texts": [incomplete, REWE]}).json()

    assert body["reading"] == 1  # the complete reading, whose items add up to the total
    assert body["items_match_total"]
    assert len(body["items"]) == 5


def test_api_needs_access_to_the_group(client, anon_client):
    assert client.post("/api/groups/999/parse-receipt", json={"text": REWE}).status_code == 404
    client.post("/api/auth/logout")
    assert anon_client.post("/api/groups/1/parse-receipt", json={"text": REWE}).status_code == 401


# --- Rules from the first real receipts (Nov 2026); invented values, real layouts ---


def amounts(text):
    return [i.amount_cents for i in parse_receipt(text, TODAY).items]


def test_price_on_the_line_below_the_name():
    receipt = parse_receipt("Kaufland\nGartenstuhl\n2 * 7,49   14,98 A\nSumme 14,98", TODAY)
    assert [(i.name, i.amount_cents) for i in receipt.items] == [("Gartenstuhl", 1498)]


def test_quantity_line_with_its_own_price_belongs_to_the_name_above():
    assert amounts("Kaufland\nGartenstuhl\n2 x 7,49   14,98 A\nSumme 14,98") == [1498]


def test_line_total_replaces_the_unit_price_above():
    text = "Gartenparadies\n3 x Katzenstreu 4.99\nPreis: 3 x 4.99 = 14.97 01\n1 x Blumentopf 6.49 01\nSumme: 21.46"
    assert amounts(text) == [1497, 649]


def test_quantity_line_above_the_item_corrects_one_digit():
    # "2 x 0,25" fits the line below it exactly, so here quantity lines stand above their item
    text = "Aldi Süd\n2 x 0,25\n80000123 Pfand 0,50 B\n4 x 1,29\n345678 Frischkäse 5,76 A\nSumme 5,66"
    assert amounts(text) == [50, 516]


def test_quantity_line_with_a_lost_count_is_tried_on_both_sides():
    assert amounts("Aldi Süd\nKäse 2,19 A\nX 1,29\nFrischkäse 5,76 A\nSumme 7,35") == [219, 516]


def test_quantity_line_that_fits_the_item_above_is_not_used_below():
    # Supermarkets print it below the item: 2 x 0,59 = 1,18 belongs to the rolls, not the noodles
    assert amounts("Rewe\nBRÖTCHEN 1,18 B\nStk x 0,59\nNUDELN 1,79 B\nSumme 2,97") == [118, 179]


def test_savings_are_no_total():
    text = "Gartenparadies\nBlumentopf 7,29 01\nRabatt -1,00\nGESAMTERSPARNIS: 1.00 EURO\nAmex 6,29"
    assert parse_receipt(text, TODAY).total_cents == 629


def test_negative_card_payment_and_a_total_below_the_items():
    # "SUMME 2,20" (a lost "7") is impossible when the items already add up to 7,20
    text = "dm\nShampoo 4,25 1\nZahnbürste 2,95 1\nSUMME EUR 2,20\nKARTENZAHLUNG EUR -7,20"
    assert parse_receipt(text, TODAY).total_cents == 720


def test_aldi_preis_line_is_no_item():
    receipt = parse_receipt("Aldi Süd\nBrot 1,25 A\nALDI PREIS 101,25\nKartenzahlung EUR 1,25", TODAY)
    assert (receipt.total_cents, [i.amount_cents for i in receipt.items]) == (125, [125])


def test_item_costing_the_whole_total_is_a_misread_payment_line():
    assert amounts("Rewe\nBrot 1,25 B\nKäse 2,00 B\nKar tersahlung EUR 3,25\nSumme 3,25") == [125, 200]


def test_minus_inside_the_text_is_no_sign():
    assert amounts("Aldi Süd\n123456 Frischkäse ,..4-2,09 A\nSumme 2,09") == [209]


@pytest.mark.parametrize("ending", ["3,79 01", "3,79%"])
def test_more_tax_code_forms(ending):
    assert amounts(f"Rewe\nKies {ending}\nSumme 3,79") == [379]


def test_unknown_store_from_its_web_address_at_the_top():
    text = "| Lo go\n12345 Musterstadt\nÖffnungszeiten: gartenparadies.de\nKies 3,79 01\nSumme 3,79"
    assert parse_receipt(text, TODAY).store == "Gartenparadies"


def test_price_without_a_readable_name_still_counts():
    receipt = parse_receipt("Rewe\nBrot 1,25 B\n| 0,50 B\nSumme 1,75", TODAY)
    assert [(i.name, i.amount_cents) for i in receipt.items] == [("Brot", 125), ("?", 50)]
    assert receipt.items_match_total
