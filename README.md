# BillBuddy

A mobile-first web app (PWA) for couples, flatmates and groups to track shared expenses,
split them fairly and see who owes whom. AI features categorize expenses automatically,
read receipts, detect recurring costs and anomalies, and forecast spending.

> **Status:** core features, accounts and web app done; AI features in progress – see [docs/project-plan.md](docs/project-plan.md)

## Features

**Core**
- Groups with any number of members (couple, flat share, trip with friends)
- Expenses with amount, date, description, payer, fixed or variable cost
- Splitting: 50/50, custom percentages, by income, or only between selected members
- Settlement: who owes whom, with as few transfers as possible
- Overview by category, person and month
- Installable on the phone's home screen (PWA)
- Personal accounts; friends join a group via invitation link and only see their own groups

**AI**
1. Automatic categorization from the description, learning from corrections
2. Receipt scan (photo → OCR → prefilled expense)
3. Forecast of spending until the end of the month
4. Detection of recurring (fixed) costs, entered automatically as standing orders
5. Detection of duplicates and unusually high expenses

## Tech stack
Python · FastAPI · SQLAlchemy + Alembic (SQLite locally, PostgreSQL online) · scikit-learn · HTML/CSS/JavaScript (PWA) · pytest

## Project structure
```
billbuddy/
  db.py            # database setup (SQLAlchemy, migrations)
  auth/            # accounts, passwords, login sessions, access control
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
migrations/        # Alembic database migrations
tests/             # pytest tests
docs/              # project plan, CRISP-DM and deployment documentation
render.yaml        # hosting configuration (Render)
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

- Web app: http://127.0.0.1:8000 – demo login: `anna@demo.local` / `demo-password`
  (exists only in the generated demo database)
- API documentation: http://127.0.0.1:8000/docs

Without `BILLBUDDY_DATABASE_URL` the app uses your private database in `data/private/billbuddy.db`.
PyCharm users find ready-made run configurations for all of these in `.run/`.

## Online: use it on your phone anywhere
BillBuddy can be hosted for free on Render (app) and Neon (database), see
**[docs/deployment.md](docs/deployment.md)**.

## Using the app on your phone in the home Wi-Fi
1. Start the server for the local network: `python -m billbuddy.serve`
   (PyCharm: *App on phone (home Wi-Fi)*). It prints the address to open, e.g. `http://192.168.0.23:8000`.
2. Open that address on a phone in the **same Wi-Fi**.
3. Add it to the home screen: Safari → Share → *Add to Home Screen* (iPhone),
   or Chrome → ⋮ → *Add to Home screen* (Android).

Without HTTPS the connection is not encrypted, so only do this in a network you trust. Offline start (service worker) only works on `localhost`
or with HTTPS, i.e. after hosting.

## AI: automatic categorization
While typing a description, the app suggests a category ("REWE City" → Groceries, 93 %).
The model – character TF-IDF + logistic regression – is trained per group on the sample data plus
the group's own categorized expenses, so every correction improves the next suggestion.
It only suggests when it is at least 70 % sure. Details: [CRISP-DM documentation](docs/crisp-dm.md)
and [evaluation report](docs/categorizer-report.md) (`python -m billbuddy.ml.categorizer.evaluate`).

## AI: month-end forecast
The overview screen shows how much will probably be spent by the end of the month – in total and
per category, with a range and a comparison with the previous months. Method: *spent so far +
median of what was spent after the same day in the previous 6 months*. In backtesting on the
sample data it is off by 9.6 % on average (simple extrapolation: 69.5 %). Details:
[CRISP-DM documentation](docs/crisp-dm.md) and [evaluation report](docs/forecast-report.md)
(`python -m billbuddy.ml.forecast.evaluate`).

## AI: fixed costs and anomalies
- **Recognized fixed costs:** payments that come back every month with a similar amount
  (same cleaned description, ~monthly gaps with little variation, amount variation ≤ 15 %). The overview
  suggests them; with one tap they become a standing order, or they are dismissed ("Keine Fixkosten").
  [Evaluation report](docs/recurring-report.md)
- **Standing orders:** fixed costs that are entered automatically every month (same amount, category,
  payer and split). They are booked when someone of the group opens the app – the free server has no
  scheduler – and missed months are caught up with their correct dates. The amount can be changed
  (e.g. rent increase) and the standing order stopped.
- **Anomalies:** before saving, the form warns about likely duplicates (same purchase entered twice) and
  unusually high amounts (IQR rule on log amounts per category, e.g. "10.8 × as much as usual – typo?").
  The overview lists the anomalies of the month. [Evaluation report](docs/anomaly-report.md)

## AI: receipt scan
"📷 Kassenbon scannen" in the expense form: the photo is read **on the phone** with Tesseract.js (the
image never leaves the device), the server parses the recognized text into store, date, total and items
and suggests a category. Items can be assigned to single people; the app turns that into the split.
The phone tries several reading settings and keeps the most plausible result (do the items add up to the
total?). With simulated OCR noise (5 %) the parser finds the total in 97.8 % of the receipts; on
simulated phone photos the whole chain found it in 5 of 6. [Evaluation report](docs/receipt-report.md)

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

All endpoints except `/api/health`, `/api/categories` and login/registration require a login
and only return groups the user belongs to.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | account and login session (cookie) |
| GET | `/api/auth/me` | the logged-in user |
| GET/POST | `/api/invites/{code}`, `/api/invites/{code}/join` | view / accept an invitation |
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
| GET | `/api/groups/{id}/suggest-category?description=…` | AI category suggestion |
| GET | `/api/groups/{id}/overview?month=2026-10` | overview per category, person and month, with forecast |
| GET/POST | `/api/groups/{id}/recurring`, `…/recurring/mark-fixed`, `…/recurring/dismiss` | recognized fixed costs / mark / dismiss |
| GET/POST | `/api/groups/{id}/recurring-rules` | standing orders / create one from an expense |
| PUT/DELETE | `/api/recurring-rules/{id}` | change the amount / stop |
| POST | `/api/groups/{id}/check-expense` | duplicate and outlier check before saving |
| GET | `/api/groups/{id}/anomalies?month=2026-10` | anomalies of a month |
| POST | `/api/groups/{id}/parse-receipt` | turn recognized receipt text into store, date, total, items |

## Privacy
Only generated sample data is part of this repository. Real expenses, databases and
secrets are excluded via `.gitignore`.

## Documentation
- [Project plan](docs/project-plan.md)
- [CRISP-DM documentation](docs/crisp-dm.md)
- [Categorizer evaluation report](docs/categorizer-report.md)
- [Forecast evaluation report](docs/forecast-report.md)
- [Recurring-cost evaluation report](docs/recurring-report.md)
- [Anomaly evaluation report](docs/anomaly-report.md)
- [Receipt scan evaluation report](docs/receipt-report.md)
- [Deployment guide](docs/deployment.md)
