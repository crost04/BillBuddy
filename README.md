# BillBuddy

A mobile-first web app (PWA) for couples, flatmates and groups to track shared expenses,
split them fairly and see who owes whom. AI features categorize expenses automatically,
read receipts, detect recurring costs and anomalies, and forecast spending.

> **Status:** early development – see [docs/project-plan.md](docs/project-plan.md)

## Features

**Core**
- Groups with any number of members (couple, flat share, trip with friends)
- Expenses with amount, date, description, payer, fixed or variable cost
- Splitting: 50/50, custom percentages, by income, or only between selected members
- Settlement: who owes whom, with as few transfers as possible
- Overview by category, person and month
- Installable on the phone's home screen (PWA)

**AI**
1. Automatic categorization from the description, learning from corrections
2. Receipt scan (photo → OCR → prefilled expense)
3. Forecast of spending until the end of the month
4. Detection of recurring (fixed) costs
5. Detection of duplicates and unusually high expenses

## Tech stack
Python · FastAPI · SQLite + SQLAlchemy · scikit-learn · HTML/CSS/JavaScript (PWA) · pytest

## Project structure
```
billbuddy/
  db.py            # database setup (SQLite + SQLAlchemy)
  data/            # sample data generator
  expenses/        # groups, members and expenses
  settlement/      # splitting and debt settlement
  api/             # REST API for the frontend
  ml/
    categorizer/   # automatic categorization
    receipt_ocr/   # receipt scan
    forecast/      # spending forecast
    recurring/     # recurring-cost detection
    anomaly/       # duplicates and outliers
frontend/          # the PWA
data/
  sample/          # generated sample data (expenses.csv)
  private/         # your real database – git-ignored, never committed
tests/             # pytest tests
docs/              # project plan and CRISP-DM documentation
```

## Getting started
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## Privacy
Only generated sample data is part of this repository. Real expenses, databases and
secrets are excluded via `.gitignore`.

## Documentation
- [Project plan](docs/project-plan.md)
- [CRISP-DM documentation](docs/crisp-dm.md)
