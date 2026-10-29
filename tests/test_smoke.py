"""Smoke test: checks that the package and all modules can be imported."""

import importlib

import pytest

MODULES = [
    "billbuddy",
    "billbuddy.expenses",
    "billbuddy.settlement",
    "billbuddy.api",
    "billbuddy.ml.categorizer",
    "billbuddy.ml.receipt_ocr",
    "billbuddy.ml.forecast",
    "billbuddy.ml.recurring",
    "billbuddy.ml.anomaly",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)
