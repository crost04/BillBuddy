"""Training data for the categorizer.

Cold start: at first the model only knows the generated sample data. Every
expense a group categorizes itself is added as training data and counts more
than a sample row, so the suggestions become more personal over time.
"""

import csv
import functools
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from billbuddy.db import PROJECT_ROOT
from billbuddy.expenses.categories import CATEGORIES
from billbuddy.expenses.models import Expense

SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "expenses.csv"
# One expense the group categorized itself counts like this many sample rows
USER_WEIGHT = 5.0


@dataclass
class TrainingData:
    descriptions: list[str] = field(default_factory=list)
    amounts: list[float] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)

    def add(self, description: str, amount: float, category: str, weight: float) -> None:
        self.descriptions.append(description)
        self.amounts.append(amount)
        self.categories.append(category)
        self.weights.append(weight)

    def __add__(self, other: "TrainingData") -> "TrainingData":
        return TrainingData(
            self.descriptions + other.descriptions,
            self.amounts + other.amounts,
            self.categories + other.categories,
            self.weights + other.weights,
        )

    def __len__(self) -> int:
        return len(self.descriptions)


@functools.cache
def sample_data() -> TrainingData:
    """The generated sample expenses (without the deliberately duplicated rows)."""
    data = TrainingData()
    with SAMPLE_CSV.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row["is_duplicate"] == "True":
                continue
            data.add(row["description"], int(row["amount_cents"]) / 100, row["category"], 1.0)
    return data


def group_data(session: Session, group_id: int) -> TrainingData:
    """Expenses of the group that have a category, i.e. that a person confirmed or chose."""
    query = select(Expense.description, Expense.amount_cents, Expense.category).where(
        Expense.group_id == group_id, Expense.category.in_(CATEGORIES)
    )
    data = TrainingData()
    for description, amount_cents, category in session.execute(query.order_by(Expense.id)):
        data.add(description, amount_cents / 100, category, USER_WEIGHT)
    return data
