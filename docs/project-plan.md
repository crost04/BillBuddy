# BillBuddy – Project Plan

Start: 29 Oct 2026 · **Deadline: 12 Dec 2026** · Team: solo

**Strategy:** get a usable app as early as possible (M1). Real-world use then shows what
to improve, while the AI features are built on top. Everything required for the
submission is done by M2, which leaves ten days of buffer before the deadline.

**Status 29 Oct:** M1 reached early – data model, sample data, expenses API, settlement, web app,
database migrations, user accounts with invitation links and the hosting setup (Render + Neon)
are done.
AI categorization and the month-end forecast with the overview screen (both CRISP-DM documented,
evaluated and live in the app) are done as well – **M2 (submission-ready) reached on 29 Oct**.
Recurring-cost and anomaly detection are done too (all four planned AI modules for the submission).
After the first real use: faster saving and standing orders (fixed costs entered automatically).
Next: German notes for the oral statement; later the receipt scan.

| Week | Dates | Focus | Modules |
|------|-------|-------|---------|
| 1 | 29 Oct – 04 Nov | Data model, sample data generator, REST endpoints for groups and expenses | `expenses`, `data`, `api` |
| 2 | 05 Nov – 11 Nov | Splitting (50/50, custom %, by income, subset of members) and settlement with minimal transfers; first frontend screens | `settlement`, `api`, `frontend` |
| 3 | 12 Nov – 18 Nov | Frontend: balances, overview, PWA install; database migrations (Alembic) so real data survives model changes | `frontend` |
| **M1** | **18 Nov** | **Usable app** – in daily use on the phone (home Wi-Fi) | |
| 4 | 19 Nov – 25 Nov | **AI 1:** automatic categorization that learns from corrections (CRISP-DM); first fixes from real use | `ml/categorizer` |
| 5 | 26 Nov – 02 Dec | **AI 2:** forecast until end of month (CRISP-DM); statistics overview (DAS) | `ml/forecast`, `frontend` |
| **M2** | **02 Dec** | **Submission-ready** – core features, categorization, forecast, statistics | |
| 6 | 03 Dec – 12 Dec | Anomaly and recurring-cost detection (statistical methods, DAS); docs polish; German bullet points for the oral statement; buffer | `ml/anomaly`, `ml/recurring`, `docs` |
| **M3** | **12 Dec** | **Submission** | |
| after | from Dec 2026 | Receipt scan (OCR), improvements based on real use | `ml/receipt_ocr` |

## DAS – data analysis and statistics
How the DAS quality criteria show up in the project:

| Criterion | Where |
|-----------|-------|
| Data quality | Validation of inputs (positive amounts, percentages sum to 100 %), data quality report (missing categories, duplicates) |
| Descriptive statistics | Overview per category, person and month: sum, mean, median, share, month-over-month comparison |
| Statistical methods | Anomaly detection (z-score / IQR), forecast via regression with an error range, recurring-cost detection via intervals |
| Model evaluation | Train/test split, cross-validation, accuracy/F1 and confusion matrix (categorizer), MAE (forecast); documented in `crisp-dm.md` |

## Open points
- Does the teacher provide a concrete list of DAS quality criteria? If so, map it onto the table above.
