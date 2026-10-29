"""Generator for realistic sample expenses (cold-start data).

The data is used to train and evaluate the AI modules before real data exists,
and to fill a demo database. Every row carries its true labels (category,
is_fixed, is_duplicate, is_outlier), so the models can be evaluated against them.

Usage:
    python -m billbuddy.data.generator                 # writes data/sample/expenses.csv
    python -m billbuddy.data.generator --db data/sample/demo.db
"""

import argparse
import csv
import datetime as dt
import math
import random
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from sqlalchemy.orm import Session

from billbuddy.auth import service as auth_service
from billbuddy.db import PROJECT_ROOT, init_db, make_engine, make_session_factory
from billbuddy.expenses.models import Expense, ExpenseShare, Group, Member

DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "sample" / "expenses.csv"

# Login for the local demo database only (sample data, not a real account)
DEMO_EMAIL = "anna@demo.local"
DEMO_PASSWORD = "demo-password"

# category: (expected purchases per month, median amount in €, spread, merchants)
VARIABLE_COSTS = {
    "Groceries": (
        12,
        38.0,
        0.5,
        [
            "Rewe",
            "Edeka",
            "Aldi Süd",
            "Aldi Nord",
            "Lidl",
            "Penny",
            "Netto",
            "Kaufland",
            "Norma",
            "Tegut",
            "Globus",
            "Alnatura",
            "Denns Biomarkt",
            "Wochenmarkt",
            "Bäckerei",
            "Metzgerei",
        ],
    ),
    "Household": (
        2,
        18.0,
        0.5,
        ["dm", "Rossmann", "Müller Drogerie", "Ikea", "Bauhaus", "Obi", "Hornbach", "Tedi", "Action"],
    ),
    "Restaurants": (
        4,
        42.0,
        0.5,
        [
            "Pizzeria",
            "Sushi Bar",
            "Döner",
            "Lieferando",
            "Wolt",
            "Uber Eats",
            "Café",
            "Burger King",
            "McDonald's",
            "Subway",
            "Vapiano",
            "Biergarten",
            "Starbucks",
        ],
    ),
    "Transport": (
        3,
        55.0,
        0.4,
        [
            "Aral",
            "Shell",
            "Esso",
            "Jet Tankstelle",
            "TotalEnergies",
            "DB Ticket",
            "Deutsche Bahn",
            "Flixbus",
            "Uber",
            "Bolt",
            "Parkhaus",
            "Tier Scooter",
            "Share Now",
        ],
    ),
    "Leisure": (
        2,
        30.0,
        0.6,
        [
            "Kino",
            "Cinemaxx",
            "Konzert",
            "Eventim",
            "Bowling",
            "Schwimmbad",
            "Museum",
            "Steam",
            "Playstation Store",
            "Kletterhalle",
        ],
    ),
    "Shopping": (
        2,
        50.0,
        0.7,
        ["Amazon", "Zalando", "H&M", "Zara", "MediaMarkt", "Saturn", "Thalia", "Otto", "About You", "Decathlon"],
    ),
    "Health": (1, 20.0, 0.6, ["Apotheke", "DocMorris", "Optiker", "Fielmann", "Zahnarzt", "Physiotherapie"]),
    "Travel": (
        0.3,
        250.0,
        0.6,
        ["Booking.com", "Airbnb", "Lufthansa", "Ryanair", "Eurowings", "Hotel", "Ferienwohnung", "TUI"],
    ),
    "Other": (0.6, 25.0, 0.8, ["Geschenk", "Post", "DHL", "Friseur", "Spende", "Blumen"]),
}

# (description, category, amount in cents, day of month)
FIXED_COSTS = [
    ("Miete", "Rent", 95000, 1),
    ("Haftpflichtversicherung", "Insurance", 650, 1),
    ("Hausratversicherung", "Insurance", 900, 1),
    ("Fitnessstudio", "Leisure", 2990, 3),
    ("Telekom Internet", "Utilities", 3995, 5),
    ("Netflix", "Subscriptions", 1399, 10),
    ("Stadtwerke Strom", "Utilities", 8500, 15),
    ("Stadtwerke Gas", "Utilities", 6500, 15),
    ("Spotify", "Subscriptions", 1799, 20),
    # Same word as the shopping merchant "Amazon": a deliberately hard case for the categorizer
    ("Amazon Prime", "Subscriptions", 899, 25),
]

# Extra spending in certain months: {month: {category: factor}}
SEASONAL_FACTORS = {
    7: {"Travel": 5.0},
    8: {"Travel": 5.0},
    11: {"Shopping": 1.3},
    12: {"Shopping": 2.5, "Restaurants": 1.3},
}
# More eating out and going out on Fridays and Saturdays
WEEKEND_FACTORS = {"Restaurants": 1.8, "Leisure": 1.8}

GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
CITIES = ["Berlin", "Hamburg", "München", "Köln", "Nürnberg"]

DUPLICATE_RATE = 0.02
OUTLIER_RATE = 0.02


@dataclass
class SampleExpense:
    date: dt.date
    description: str
    amount_cents: int
    category: str
    payer: str
    is_fixed: bool
    is_duplicate: bool = False
    is_outlier: bool = False
    # The shop behind the description; lets the evaluation test on unseen shops
    merchant: str = ""


def generate_expenses(
    start: dt.date,
    end: dt.date,
    members: tuple[str, ...] = ("Anna", "Ben"),
    seed: int = 42,
) -> list[SampleExpense]:
    """Create sample expenses between start and end (both inclusive).

    The same seed always gives the same data, so results are reproducible.
    """
    rng = random.Random(seed)
    expenses = []

    day = start
    while day <= end:
        expenses += _fixed_costs_on(day, members)
        expenses += _variable_costs_on(day, members, rng)
        day += dt.timedelta(days=1)

    expenses = _add_anomalies(expenses, rng)
    expenses.sort(key=lambda e: e.date)
    return expenses


def _fixed_costs_on(day: dt.date, members) -> list[SampleExpense]:
    result = []
    for i, (name, category, amount_cents, day_of_month) in enumerate(FIXED_COSTS):
        if day.day != day_of_month:
            continue
        description = f"{name} {GERMAN_MONTHS[day.month - 1]}" if category == "Rent" else name
        # Each fixed cost is always paid by the same person
        payer = members[i % len(members)]
        result.append(SampleExpense(day, description, amount_cents, category, payer, is_fixed=True, merchant=name))
    return result


def _variable_costs_on(day: dt.date, members, rng: random.Random) -> list[SampleExpense]:
    result = []
    is_weekend = day.weekday() in (4, 5)
    for category, (per_month, median, spread, merchants) in VARIABLE_COSTS.items():
        rate = per_month / 30
        rate *= SEASONAL_FACTORS.get(day.month, {}).get(category, 1.0)
        if is_weekend:
            rate *= WEEKEND_FACTORS.get(category, 1.0)
        if rng.random() >= min(rate, 0.95):
            continue

        # Log-normal: most amounts are near the median, a few are much larger
        amount_cents = max(50, round(median * math.exp(rng.gauss(0, spread)) * 100))
        merchant = rng.choice(merchants)
        description = _vary_description(merchant, amount_cents, rng)
        result.append(
            SampleExpense(
                day, description, amount_cents, category, rng.choice(members), is_fixed=False, merchant=merchant
            )
        )
    return result


def _vary_description(merchant: str, amount_cents: int, rng: random.Random) -> str:
    """Write the same merchant in different ways, like people do."""
    amount = f"{amount_cents / 100:.2f}".replace(".", ",")
    template = rng.choice(["{m}", "{m}", "{m}", "{m} {city}", "{m} Kartenzahlung", "{m} {amount}"])
    text = template.format(m=merchant, city=rng.choice(CITIES), amount=amount)
    style = rng.random()
    if style < 0.15:
        return text.upper()
    if style < 0.30:
        return text.lower()
    return text


def _add_anomalies(expenses: list[SampleExpense], rng: random.Random) -> list[SampleExpense]:
    """Insert labelled duplicates and outliers for the anomaly detection."""
    result = []
    for expense in expenses:
        if expense.is_fixed:
            result.append(expense)
            continue
        if rng.random() < OUTLIER_RATE:
            expense.amount_cents = round(expense.amount_cents * rng.uniform(4, 8))
            expense.is_outlier = True
        result.append(expense)
        if not expense.is_outlier and rng.random() < DUPLICATE_RATE:
            result.append(SampleExpense(**{**asdict(expense), "is_duplicate": True}))
    return result


def write_csv(expenses: list[SampleExpense], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [f.name for f in fields(SampleExpense)]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for expense in expenses:
            writer.writerow(asdict(expense))


def load_into_db(expenses: list[SampleExpense], session: Session, group_name: str = "Demo") -> Group:
    """Save the expenses as a new group; every expense is split equally between all members."""
    member_names = sorted({e.payer for e in expenses})
    members = {name: Member(name=name) for name in member_names}
    group = Group(name=group_name, members=list(members.values()))
    for e in expenses:
        group.expenses.append(
            Expense(
                payer=members[e.payer],
                amount_cents=e.amount_cents,
                date=e.date,
                description=e.description,
                category=e.category,
                is_fixed=e.is_fixed,
                shares=[ExpenseShare(member=m) for m in members.values()],
            )
        )
    session.add(group)
    session.commit()
    return group


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BillBuddy sample expenses.")
    parser.add_argument("--months", type=int, default=24, help="number of months up to today")
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducible data")
    parser.add_argument("--out", type=Path, default=DEFAULT_CSV_PATH, help="CSV output file")
    parser.add_argument("--db", type=Path, help="also load the data into this SQLite file (replaces it)")
    args = parser.parse_args()

    end = dt.date.today()
    start = _first_of_month(end, months_back=args.months - 1)
    expenses = generate_expenses(start, end, seed=args.seed)

    write_csv(expenses, args.out)
    print(f"Wrote {len(expenses)} expenses ({start} to {end}) to {args.out}")

    if args.db:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        args.db.unlink(missing_ok=True)
        engine = make_engine(f"sqlite:///{args.db}")
        init_db(engine)
        with make_session_factory(engine)() as session:
            group = load_into_db(expenses, session)
            user = auth_service.register(session, DEMO_EMAIL, "Anna", DEMO_PASSWORD)
            group.members[0].user_id = user.id
            session.commit()
        print(f"Loaded them into {args.db} – log in as {DEMO_EMAIL} / {DEMO_PASSWORD}")


def _first_of_month(day: dt.date, months_back: int) -> dt.date:
    month_index = day.year * 12 + day.month - 1 - months_back
    return dt.date(month_index // 12, month_index % 12 + 1, 1)


if __name__ == "__main__":
    main()
