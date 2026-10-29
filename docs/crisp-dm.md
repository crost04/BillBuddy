# CRISP-DM Documentation

This document records what we did and decided in each CRISP-DM phase for every AI module.
It is the basis for the oral statement on AI development.

**Cold-start strategy (all modules):** we start with self-generated sample data
(`data/sample/`, created by `billbuddy/data/generator.py`), and later the models keep learning from
real entries. Real entries stay in the private database and never end up in the repository.

The six phases:
1. **Business Understanding** – What problem do we solve, and how do we measure success?
2. **Data Understanding** – What data do we have, and what does it look like?
3. **Data Preparation** – Cleaning, features, train/test split
4. **Modeling** – Which algorithms we tried and why
5. **Evaluation** – Metrics, results, and whether the business goal is met
6. **Deployment** – How the model is integrated into the app and updated

---

## 1. Categorizer (`ml/categorizer`)
Full numbers: [categorizer-report.md](categorizer-report.md) (regenerate with
`python -m billbuddy.ml.categorizer.evaluate`).

### Business Understanding
- **Problem:** choosing a category for every expense is tedious, so people skip it – and without
  categories there is no overview or forecast.
- **Goal:** suggest the category automatically from the description ("Rewe 34,50" → Groceries) and
  learn from the user's own choices.
- **Success criteria:** on the sample data, macro F1 ≥ 85 % and clearly better than a baseline;
  in real use, most suggestions are kept (acceptance rate, measured in the app). A wrong suggestion is
  worse than none, because the user has to notice and correct it.

### Data Understanding
- Cold start: no real data yet, so we generated 24 months of sample expenses for a couple
  (940 rows, 96 shops, 13 categories), with labels (true category, shop) for evaluation.
- Findings: descriptions are short (1–2 words), written inconsistently ("REWE", "rewe",
  "Rewe Kartenzahlung", "Rewe 34,50"), and the classes are strongly imbalanced
  (Groceries 32 %, Travel 0.8 %).
- Limitation: generated data is cleaner and less varied than real data, so results on it are optimistic.

### Data Preparation
- Removed the deliberately duplicated rows (otherwise identical rows end up in training and test data).
- Text cleaning (`preprocessing.py`): lower case, remove digits, punctuation and noise words such as
  "Kartenzahlung".
- Features: TF-IDF on character groups of 2–5 letters, which also works for typos and new spellings.
- Training data in the app: sample data (weight 1) plus the group's own categorized expenses
  (weight 5), so personal data quickly outweighs the sample data.

### Modeling
- Compared with 5-fold stratified cross-validation: a baseline (always "Groceries"), word TF-IDF +
  logistic regression, character TF-IDF + naive Bayes, character TF-IDF + logistic regression, and the
  same with the amount as an additional feature.
- `class_weight="balanced"` so rare categories are not ignored.
- **Chosen:** character TF-IDF + logistic regression – best accuracy together with the amount variant,
  but simpler; it also returns probabilities that serve as confidence.
- The amount brought no measurable benefit (also not for unseen shops), so we left it out
  (simpler model with the same quality). It stays available to re-test with real data.

### Evaluation
- Known shops: accuracy 99.0 %, macro F1 95.3 % (baseline: 31.6 % / 3.7 %) → success criterion met.
- Weak spot: Travel (only 7 examples, recall 57 %); mistakes mainly between similar categories
  (Travel ↔ Transport).
- **Unseen shops** (grouped cross-validation by shop): only 30 % accuracy. The model recognizes
  shops, it does not "understand" what a shop sells. Consequence: learn from the user's choices and
  make no suggestion when unsure.
- **Confidence threshold:** raised from 0.5 to 0.7. Known shops still get a suggestion in 97 % of the
  cases (99.9 % correct); for unseen shops, correct suggestions rise from 65 % to 80 %.
- Learning curve: with 100 examples macro F1 is about 62 %, with 400 about 90 % → the sample data is
  needed for the cold start.

### Deployment
- The model is trained per group in the server's memory (0.2 s) from the sample data plus the group's
  categorized expenses. It is retrained automatically as soon as the group's categories change, so
  every correction is used immediately. No model file is stored, so no personal data ends up on disk
  or in the repository.
- The expense form asks the API for a suggestion while the user types and shows it with its
  confidence; the user can always change it.
- The suggested category is stored with each expense, so the acceptance rate (suggestion kept vs.
  changed) can be measured on real data.
- Risks and next steps: feedback loop (accepted wrong suggestions become training data), re-evaluate
  with real data after a few weeks, re-test the amount feature.

## 2. Forecast (`ml/forecast`)
Full numbers: [forecast-report.md](forecast-report.md) (regenerate with
`python -m billbuddy.ml.forecast.evaluate`).

### Business Understanding
- **Problem:** in the middle of the month nobody knows whether spending is on track – the
  bank balance only shows the past.
- **Goal:** forecast the month-end total and every category, with a range, and compare it with
  the previous months ("more or less than usual?").
- **Success criteria:** clearly better than simple methods (extrapolation, average of previous
  months) in backtesting; a range that is honest (the real result lands inside it in roughly
  two out of three cases).

### Data Understanding
- Same sample data as the categorizer (22 complete months).
- Monthly totals vary a lot (coefficient of variation 0.30); fixed costs (rent, insurance,
  utilities) are constant, travel and shopping vary strongly.
- **Spending is not spread evenly:** 38 % of a month's total is spent on the 1st (rent), 71 % by
  the 15th.
- Seasonality: July is clearly higher (holidays); with real data a full year is needed to see it.

### Data Preparation
- Duplicates removed; each expense reduced to date, category and amount (`Record`).
- History = up to 6 complete previous months. The group's first month is left out, because it
  is probably incomplete (nobody starts using the app on the 1st).
- For the backtesting only the data known on the simulated day is used (no look into the future).

### Modeling
- Compared in backtesting (16 months × days 5, 10, 15, 20, 25): extrapolation, mean of previous
  months, last month, linear regression (trained only on earlier months), and
  "spent so far + typical rest" with mean or median.
- **Chosen:** spent so far + **median** of what was spent after the same day in the previous
  months. It combines what is known about this month with the typical rest – including fixed
  costs that are still due. The median is robust against single unusual months.
- Range: ± one standard deviation of the rest.
- The linear regression was worse: with one example per month there is too little data, so it
  learns noise. The simpler method wins.

### Evaluation
- MAPE of the month total: **9.6 %** (extrapolation 69.5 %, mean of previous months 15.0 %,
  linear regression 12.9 %) → success criterion met.
- Accuracy improves over the month: 13.5 % on day 5, 4.5 % on day 25.
- The range contains the real result in 61 % (total) and 77 % (categories) of the cases –
  close to the ~68 % that ± one standard deviation promises.
- Limitations: seasonality is not modeled (a July after a quiet spring is underestimated);
  single big purchases cannot be predicted.

### Deployment
- The overview screen calls `/api/groups/{id}/overview`; the forecast is calculated on the fly
  from the group's expenses (milliseconds, no stored model, nothing to retrain).
- Shown per category: spent so far, forecast with range, and the average of the previous months.
- Cold start: without a complete previous month, the app shows only what was spent and says
  that a forecast needs more data; with 1–2 months it marks the forecast as uncertain.
- Next steps: re-run the backtesting on real data after a few months; add seasonality once a
  full year of data exists.

## 3. Recurring-cost detection (`ml/recurring`)
Full numbers: [recurring-report.md](recurring-report.md) (regenerate with
`python -m billbuddy.ml.recurring.evaluate`).

### Business Understanding
- **Problem:** people forget to mark fixed costs, and they lose track of subscriptions.
- **Goal:** recognize expenses that come back every month, suggest marking them as fixed costs and
  show when the next payment is due.
- **Success criteria:** high precision (a false suggestion annoys), all fixed costs found after a few
  months.

### Data Understanding
- 940 sample expenses → 191 different descriptions after cleaning; 10 fixed costs.
- 71 variable descriptions also appear at least 3 times (e.g. "rewe") – counting alone is not enough.
- Fixed costs: gap ~31 days with almost no variation (std 0.9 days) and a constant amount;
  frequent variable expenses: irregular gaps (std 64 days) and changing amounts (CV 0.47).

### Data Preparation
- Descriptions cleaned like for the categorizer, plus month names removed
  ("Miete Oktober" = "MIETE November" = "miete"), so every payment of a series gets the same key.
- Per key: sorted dates → gaps in days; amounts → coefficient of variation.

### Modeling
- Statistical rules instead of a trained model – the data separates clearly, and rules are easy to
  explain and need no training data: at least 3 times, median gap 26–35 days, gap standard deviation
  ≤ 5 days, amount variation ≤ 15 %.
- A series counts as cancelled if more than one payment is missing.

### Evaluation
- Ablation (adding one rule at a time): counting alone 12 % precision; + monthly gap 56 %;
  + regular gaps **100 % precision and recall**.
- The amount rule changes nothing on the sample data; it is kept for real cases the generator does not
  produce (a monthly online order with very different amounts – covered by a unit test).
- Robust against messier data: weekend shifts and price increases (+8 %) change nothing.
- A fixed cost is recognized after 3 payments, i.e. in the third month.
- 100 % is optimistic because the sample data is tidy; the real test is daily use.

### Deployment
- The overview screen lists the recognized fixed costs with amount, day and next payment; with one tap
  all payments of a series are marked as fixed costs.
- Calculated on the fly from the group's expenses (no stored model).
- Next steps: quarterly and yearly payments (need more than a year of data).

## 4. Anomaly detection (`ml/anomaly`)
Full numbers: [anomaly-report.md](anomaly-report.md) (regenerate with
`python -m billbuddy.ml.anomaly.evaluate`).

### Business Understanding
- **Problem:** the same purchase is entered twice (both partners), or a typo turns 34.50 € into
  345 € – both distort balances, overview and forecast.
- **Goal:** warn **before saving** and list anomalies in the overview.
- **Success criteria:** few false alarms (every alarm interrupts the user), most real anomalies found.

### Data Understanding
- The generator inserted 13 duplicates and 12 unusually high amounts (4–8 × normal) and marked them.
- Amounts are skewed (many small, few large); on the log scale they are roughly symmetric.
- 1 outlier is smaller than the largest normal expense of its category and 1 is in a category with
  too little data (travel) – no amount-based method can find these two.

### Data Preparation
- Duplicates: descriptions cleaned (as for the categorizer), so "REWE Kartenzahlung" = "Rewe".
- Outliers: each category separately (300 € for groceries is unusual, for a hotel it is not); log of
  the amount; categories with fewer than 8 expenses are skipped.

### Modeling
- Duplicates: same cleaned description and same amount, at most one day apart.
- Outliers – compared: z-score, IQR rule on euros, Isolation Forest (machine learning), robust
  z-score (median/MAD) with 3.5 and 3.0, IQR rule on log amounts.
- **Chosen: IQR rule on log amounts** (outlier if log amount > Q3 + 1.5 · IQR). We had first picked the
  robust z-score with the literature value 3.5; the evaluation showed that it missed half of the
  outliers, so we switched.

### Evaluation
- Outliers: IQR on log amounts 10 of 11 found, 1 false alarm (F1 91 %); robust z (3.5) only 6 of 11;
  z-score with mean/standard deviation suffers from masking; IQR on euros 19 false alarms; Isolation
  Forest with default settings 132 false alarms (it needs the share of outliers in advance).
- Duplicates: realistic variants (other spelling, one day later) – exact comparison finds only 3 of 13,
  the chosen method all 13 without false alarms.
- Caution: method choice and evaluation use the same 11 outliers, so small differences are not
  reliable; to be checked again with real data.

### Deployment
- When saving an expense, the app checks for duplicates and unusual amounts and asks
  "Trotzdem speichern?" with an explanation (e.g. "9 × so viel wie üblich bei Lebensmitteln").
- The overview lists anomalies of the month with a link to the expense.
- Statistics are calculated on the fly from the group's expenses.

## 5. Receipt scan (`ml/receipt_ocr`)
| Phase | What we did / decided |
|-------|-----------------------|
| Business Understanding | _TBD_ |
| Data Understanding | _TBD_ |
| Data Preparation | _TBD_ |
| Modeling | _TBD_ |
| Evaluation | _TBD_ |
| Deployment | _TBD_ |
