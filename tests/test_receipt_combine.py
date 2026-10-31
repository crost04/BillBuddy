"""Tests for combining several OCR readings of one receipt (billbuddy.ml.receipt_ocr.combine)."""

import datetime as dt

from billbuddy.ml.receipt_ocr.combine import combine
from billbuddy.ml.receipt_ocr.parser import Receipt, ReceiptItem


def items(*amounts):
    return [ReceiptItem(f"Artikel {n}", cents) for n, cents in enumerate(amounts)]


def test_total_store_and_date_by_majority():
    day = dt.date(2026, 10, 29)
    readings = [
        Receipt("Aldi Süd", day, 1250, items(100)),
        Receipt(None, dt.date(2026, 10, 20), 81250, items(100)),  # misread total
        Receipt("Aldi Süd", day, 1250, items(100)),
    ]
    receipt, _ = combine(readings)
    assert (receipt.store, receipt.date, receipt.total_cents) == ("Aldi Süd", day, 1250)


def test_tie_goes_to_the_earlier_reading():
    receipt, _ = combine([Receipt("Aldi Süd", None, 500, []), Receipt("Netto", None, 600, [])])
    assert (receipt.store, receipt.total_cents) == ("Aldi Süd", 500)


def test_items_from_the_reading_that_adds_up_to_the_agreed_total():
    readings = [
        Receipt(total_cents=600, items=items(100, 200, 250, 300)),  # more items, but one is wrong
        Receipt(total_cents=600, items=items(100, 200, 300)),
        Receipt(total_cents=None, items=items(100)),
    ]
    receipt, reading = combine(readings)
    assert reading == 1
    assert receipt.items_match_total


def test_without_a_match_the_reading_with_the_most_items_wins():
    readings = [Receipt(total_cents=1000, items=items(100)), Receipt(total_cents=1000, items=items(100, 200))]
    receipt, reading = combine(readings)
    assert reading == 1
    assert not receipt.items_match_total


def test_no_readings():
    receipt, reading = combine([])
    assert (receipt, reading) == (Receipt(), None)


# --- Repair: items from other readings, accepted only if the sum is then exact ---


def named(*pairs):
    return [ReceiptItem(name, cents) for name, cents in pairs]


def amounts(receipt):
    return [i.amount_cents for i in receipt.items]


def test_a_misread_price_is_replaced_when_the_items_then_add_up():
    readings = [
        Receipt(total_cents=540, items=named(("Spülmittel", 145), ("Zahnbürste", 175), ("Kaugummi", 120))),
        Receipt(total_cents=540, items=named(("Spülmittel", 145), ("Zahnbürste", 275))),  # lost a line
    ]
    receipt, reading = combine(readings)
    assert reading == 0
    assert amounts(receipt) == [145, 275, 120]
    assert receipt.items_match_total


def test_a_line_lost_by_the_best_reading_is_inserted_in_its_place():
    readings = [
        Receipt(total_cents=744, items=named(("Brot", 210), ("Käse", 300), ("Äpfel", 99))),
        Receipt(total_cents=744, items=named(("Brot", 210), ("Milch", 135))),
    ]
    receipt, _ = combine(readings)
    assert [(i.name, i.amount_cents) for i in receipt.items] == [
        ("Brot", 210),
        ("Milch", 135),
        ("Käse", 300),
        ("Äpfel", 99),
    ]


def test_two_misread_prices_are_replaced_together():
    readings = [
        Receipt(total_cents=745, items=named(("Brot", 210), ("Käse", 200), ("Milch", 135))),
        Receipt(total_cents=745, items=named(("Brot", 310), ("Käse", 200), ("Milch", 135))),
        Receipt(total_cents=745, items=named(("Brot", 210), ("Käse", 300), ("Milch", 135))),
    ]
    receipt, _ = combine(readings)
    assert amounts(receipt) == [310, 300, 135]


def test_a_value_that_only_brings_the_sum_closer_is_not_taken():
    # 2,40 instead of 2,10 brings the items to 5,90 – close to 6,00, but not exact
    readings = [
        Receipt(total_cents=600, items=named(("Brot", 210), ("Käse", 300), ("Salz", 50))),
        Receipt(total_cents=600, items=named(("Brot", 240), ("Käse", 300))),
    ]
    receipt, reading = combine(readings)
    assert reading == 0
    assert amounts(receipt) == [210, 300, 50]


def test_an_ambiguous_repair_changes_nothing():
    # +1,00 on the bread or +1,00 on the cheese would both fit: better leave the gap visible
    readings = [
        Receipt(total_cents=610, items=named(("Brot", 210), ("Käse", 300))),
        Receipt(total_cents=610, items=named(("Brot", 310), ("Käse", 400))),
    ]
    receipt, _ = combine(readings)
    assert amounts(receipt) == [210, 300]
    assert not receipt.items_match_total
