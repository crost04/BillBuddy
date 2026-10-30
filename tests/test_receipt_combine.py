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
