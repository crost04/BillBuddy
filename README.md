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
frontend/          # the PWA (HTML, CSS, JavaScript – no build step)
  js/api.js        # calls to the backend
  js/views/        # one file per screen
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

# Generate sample data and a demo database
python -m billbuddy.data.generator --db data/sample/demo.db

# Start the app on the demo database
BILLBUDDY_DATABASE_URL=sqlite:///data/sample/demo.db uvicorn billbuddy.api.main:app --reload
```

- Web app: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/docs

Without `BILLBUDDY_DATABASE_URL` the app uses your private database in `data/private/billbuddy.db`.
PyCharm users find ready-made run configurations for all of these in `.run/`.

## Using the app on your phone
1. Start the server for the local network: `python -m billbuddy.serve`
   (PyCharm: *App on phone (home Wi-Fi)*). It prints the address to open, e.g. `http://192.168.0.23:8000`.
2. Open that address on a phone in the **same Wi-Fi**.
3. Add it to the home screen: Safari → Share → *Add to Home Screen* (iPhone),
   or Chrome → ⋮ → *Add to Home screen* (Android).

Only do this in a network you trust: there is no login yet, so everyone in the same
Wi-Fi could open the app. Offline start (service worker) only works on `localhost`
or with HTTPS, i.e. after hosting.

## How settlement works
1. **Split:** every expense is divided among its participants (equally, by percentage or
   by income). Parts are exact to the cent: leftover cents go to the parts with the largest
   remainder, so 10.00 € / 3 becomes 3.34 + 3.33 + 3.33.
2. **Balance:** per member, *paid* minus *own share*, plus recorded payments.
   Positive means the member gets money back; all balances add up to 0.
3. **Transfers:** the member who owes the most pays the member who is owed the most,
   until everyone is even – at most *n − 1* transfers for *n* members.

## API overview
Interactive documentation: `http://127.0.0.1:8000/docs`

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/groups` | list / create groups |
| GET/DELETE | `/api/groups/{id}` | read / delete a group |
| POST | `/api/groups/{id}/members` | add a member |
| PUT | `/api/members/{id}` | rename a member, set income |
| GET/POST | `/api/groups/{id}/expenses` | list (optionally `?month=2026-10`) / add expenses |
| GET/PUT/DELETE | `/api/expenses/{id}` | read / edit / delete an expense |
| GET | `/api/groups/{id}/settlement` | balances and suggested transfers |
| GET/POST | `/api/groups/{id}/payments` | list / record payments between members |
| DELETE | `/api/payments/{id}` | delete a payment |
| GET | `/api/categories` | available categories |

## Privacy
Only generated sample data is part of this repository. Real expenses, databases and
secrets are excluded via `.gitignore`.

## Documentation
- [Project plan](docs/project-plan.md)
- [CRISP-DM documentation](docs/crisp-dm.md)
