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
- The model is trained per group in the server's memory from the sample data plus the group's
  categorized expenses. No model file is stored, so no personal data ends up on disk or in the
  repository.
- When the group's categories change, the model is retrained in a background thread (at most once a
  minute) while the previous model keeps answering. Reason: on the free server (a fraction of one CPU)
  training takes seconds, and in real use it slowed down saving – a finding from the user's own testing.
  So a correction is used within about a minute instead of immediately.
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
- The overview screen suggests the recognized fixed costs with amount, day and next payment.
- Real use showed a gap: the detection only works if fixed costs are entered by hand every month.
  So a recognized series can now be turned into a **standing order** with one tap – from then on the
  app enters it automatically every month. A wrong suggestion can be dismissed ("Keine Fixkosten"),
  so the user stays in control and false positives cost one tap.
- Calculated on the fly from the group's expenses (no stored model).
- Next steps: quarterly and yearly payments (need more than a year of data); measure how often
  suggestions are accepted or dismissed.

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
Full numbers: [receipt-report.md](receipt-report.md) (regenerate with
`python -m billbuddy.ml.receipt_ocr.evaluate`).

### Business Understanding
- **Problem:** typing in a long receipt is tedious, and splitting it ("the beer is mine, the shampoo
  hers") is even more so.
- **Goal:** take a photo → amount, store, date and category are filled in, and single items can be
  assigned to people, which turns into the split of the expense.
- **Success criteria:** the total is right in most scans; the app tells the user when to double-check.
- **Constraint:** the free server (a fraction of one CPU, 512 MB) is far too weak for text recognition.

### Data Understanding
- No real receipts yet (cold start), and real receipts contain personal data. So synthetic receipts
  imitate the layouts of German shop types (supermarket, discounter, drugstore, bakery): quantity lines,
  deposit, discounts, cash with change, VAT lines, two date formats. Since the fourth real test the
  drugstore layout has its own style: the tax rate as a digit behind the price ("2,45 1"), quantity and
  unit price in front of the name ("3x 0,85 Fruchtgummi"), a subtotal with a discount below it.
- Typical OCR mistakes on receipt photos were simulated: confused characters (0↔O, 1↔l, 5↔S),
  missing or extra spaces, lost lines – in noise levels from 0 to 10 %.

### Data Preparation
- Every recognized line is cleaned: letters inside numbers are turned back into digits ("l,99" → "1,99"),
  spaces inside amounts removed, capitals made readable ("BIER 6ER" → "Bier 6er").
- On the phone, the photo is scaled by its width (so the print stays large enough), turned into grayscale
  and binarized with an **adaptive threshold** (Bradley–Roth), which copes with shadows and uneven
  light; Tesseract straightens tilted photos (`rotateAuto`).
- Since the third iteration the phone first **cuts away the table left and right of the receipt**:
  paper = brighter than Otsu's threshold and not colourful; the columns that are mostly paper are the
  receipt. Only left and right are cut, because top to bottom a shadow could look like the end of the
  receipt and cut off the total.
- Item lines: article numbers in front of the names are removed ("123456 Mineralwasser" →
  "Mineralwasser"), decimal separators misread as other marks are repaired ("1:09 A", "1'79" → 1,09 /
  1,79; "119 A" → 1,19), and
  "ß"/"8" are accepted as the tax code "B". Tax codes printed as digits ("2,45 1") and up to three
  marks OCR reads from the paper edge behind the price ("2,35 | I", "4,60 ;") are accepted too;
  a number followed by a word ("3x 0,85 Fruchtgummi") or a weight with three decimals stays no price.

### Modeling
- **Architecture decision:** text recognition with **Tesseract.js in the browser of the phone** (fast,
  free, and the photo never leaves the phone); the server only receives the text. Server-side
  Tesseract or EasyOCR would not fit the free server.
- **Parser** with rules: known shop names (tolerant of OCR mistakes), the first plausible date, the total
  line found by keywords ("zu zahlen", "Summe", "Gesamt", …), items = lines with an amount above the
  total (quantity lines are skipped).
- Items end at the total line **or at the card-payment slip**, whichever comes first (some discounters print
  "K-U-N-D-E-N-B-E-L-E-G … Kartenzahlung … Betrag" between the items and "Summe"). If the total appears
  twice (e.g. "Summe" and the card payment), no item may cost more than the total plus the discounts.
  "Zwischensumme" is no item; discounts below it are (negative), so the items still add up to the total.
- The total: the best keyword wins ("zu zahlen" before "Summe" before "Betrag") – unless another
  amount is confirmed more often: "Summe 812,50" (a mark read as "8") loses against "Betrag 12,50" and
  "girocard 12,50".
- The store is also searched further down the receipt ("ALDI SÜD - Gutes für alle"), and long store
  names may have one wrong letter ("ALDI SOD"). "SÜD", "SUED" and "SUD" count as the same. Short names
  like "dm" are only taken from the top or from the web address at the bottom ("dm.de").
- **Ensemble of readings** (`combine.py`): the phone reads the photo up to four times; total, store
  and date are decided by majority, the items come from the reading whose items add up to the total
  (otherwise the one with the most items).
- Plausibility checks: do the items add up to the total? Is a price with quantity and unit price in
  front of the name a multiple of the unit price? ("3x 0,85 … 2,59" → 2,55: corrected only when
  exactly one digit differs, because 5 and 9 look alike on thermal paper.)
- Category: the store name goes through the categorizer (module 1).
- Item assignment: items for one person are charged to that person, the rest (and any difference to
  the total) is shared; the result becomes a percentage split, exact to the cent.

### Evaluation
- Without noise everything is right; at 5 % noise (current version, with the drugstore layout since
  31 Oct 2026): total 97.5 %, items F1 97.0 %, store 88.8 %, date 85.8 %.
- **Iteration:** the first parser version found the total in only 79.0 % of the receipts at 5 % noise,
  because OCR split "SUMME" into "S UMME". Tolerant keyword matching (spaces ignored, one wrong letter
  allowed) and digit repair in dates raised it to 94.5 %; taking the total from the payment line when
  the total line is lost (card payment = total, cash = given minus change) raised it to 97.8 %.
- Naive approaches are much worse: "largest amount = total" 29–38 % (fails with cash payments),
  "first line = store" 35–50 %.
- When the plausibility check passes, the total was right in every case – so the app can say
  "✅ die Summe passt" or "⚠️ bitte prüfen".
- End-to-end test in the browser: a drawn receipt image went through Tesseract.js, the parser and the
  form in about 5 seconds, all fields correct.
- **First real test (iPhone, 29 Oct 2026): values were recognized wrongly.** The image preparation only
  raised the contrast of the whole photo and scaled it by its longest side; on real photos shadows,
  tilt and small print broke the recognition.
- **Second iteration – photo test in the browser** with simulated phone photos (receipt tilted 2–4°,
  blurred, shadow across the paper, speckles, JPEG compression, receipt only in the middle of the
  picture), 6 receipts:
  - first version: total right in 0 of 6, no items found;
  - adaptive threshold (every pixel compared with its surroundings, against shadows) + automatic
    straightening (`rotateAuto`): depending on the page mode 0–5 of 6;
  - tuning on 3 photos and testing on 3 new ones showed **overfitting**: the best setting for the first
    photos failed on the new ones – and which page mode was best changed between photo sets;
  - **chosen: several reading attempts, the most plausible result wins**, judged by the parser's own
    check (items add up to the total): total right in 5 of 6, items 22 of 30, about 2 s per receipt
    (up to 3 attempts). The one wrong total was flagged by the check, so the app showed
    "⚠️ bitte prüfen" instead of silently saving a wrong amount.
- **Second real test (iPhone, same day):** with the improved version the user reported that the scan
  now works better on the same receipt.
- Simulated photos are only a rough stand-in for real ones; a systematic measurement with several real
  receipts is still open.
- **Third real test (receipt from a discounter, 30 Oct 2026): "noch nicht optimal".** The items added
  up to many times the total, not all products were found, and the store name was read without its
  umlaut and not recognized. The photo was examined locally (it stays out of the repository, like all
  amounts and products on it) and run through the same recognition as on the phone. Findings:
  - the receipt covered only a third of the photo's width; the wood grain of the table was read as
    fantasy text (e.g. "EZ REES a SZ Sn") and the letters were small;
  - the text recognition itself was mostly right – most losses came from the **parser**: article
    numbers in front of the names, "ß" instead of the tax code "B", ":" instead of the decimal comma,
    an item line starting with "6x" taken for a quantity line, the umlaut-less store name;
  - page mode 3 (automatic layout) read all prices as a separate column after the names – useless for
    receipts, so it was replaced by page mode 4 on the unprocessed image.
- **Measurement** (true values typed off the receipt: 28 item lines, total, date, store; the photo in 4
  variants – original 24 MP, 12 MP, tilted 2°, darker – so that the settings are not tuned to one
  single picture):

  | Version | Items found (of 28, mean) | Total | Date | Store |
  |---|---|---|---|---|
  | before | 23.5 | 4 of 4 | 4 of 4 | 0 of 4 |
  | new parser only | 25.5 | 4 of 4 | 4 of 4 | 4 of 4 |
  | new parser + cut-out receipt (1200 px wide) + new page modes **(chosen)** | 25.8 | 4 of 4 | 4 of 4 | 4 of 4 |

  The parser brought most of the gain; the cut-out added little on this receipt (within the
  variation between photo variants) but removes the fantasy text from the background. The two lines
  still missing (the same product twice) are hard to read in every variant. On the synthetic receipts the
  new parser is as good as before (items F1 at 5 % noise 97.5 % vs 97.6 %) and finds the store more
  often (89.2 % vs 86.8 %).
- **Discarded idea:** taking single items from different readings (aligning the item lists and filling
  gaps) made the result *worse* on the real receipt: a misread amount from another reading sometimes
  happened to bring the sum closer to the total and was taken over. So only total, store and date are
  voted on.
- **Fourth real test (drugstore receipt, 31 Oct 2026): "erkennt nicht alle Bestandteile".** Four
  products and a discount, but the app showed only the discount, so nothing could be assigned to a
  person. The photo was examined locally again (it stays out of the repository). Findings:
  - the text recognition read all four prices correctly – the **parser** threw them away: the shop
    prints the tax rate as a digit behind the price ("2,45 1"), and only letters were allowed there;
  - "Zwischensumme" was taken for an item and then dropped by the "no item dearer than the total"
    rule – which itself was wrong for receipts with a discount (found by the synthetic drugstore
    receipts: an item may cost more than the total when a discount follows);
  - on the photo variants, single digits were misread ("5" as "9"), and which image size read them
    right differed from variant to variant.
- **Measurement** on this receipt (true values typed off: 5 item lines incl. the discount; the same
  4 photo variants as before; the phone stops as soon as the items add up to the total):

  | Version | Items found (of 5, mean) | All items right | Total, date, store |
  |---|---|---|---|
  | before | 1.0 | 0 of 4 | 4 of 4 |
  | new parser | 4.0 | 2 of 4 | 4 of 4 |
  | new parser + second reading at 1600 px instead of 1200 px **(chosen)** | 4.75 | 3 of 4 | 4 of 4 |

  The original photo is read completely in the first attempt (about 5 seconds). The discounter receipt
  stays at 26 of 28 items (26.3 before: one item less over 4 variants, within the variation). Six attempt
  lists were compared on both receipts; smoother downscaling of the photo ("high" image smoothing) was
  tried and made the results worse at 1200 px.
- Synthetic receipts with the new drugstore layout, previous vs new parser: items F1 without noise
  87.7 % → 100 %, at 5 % noise 88.8 % → 97.0 %.
- Shown to the user when items are missing: "Betrag laut Bon: 12,34 € – bitte kurz prüfen", so it is
  clear that the amount comes from the receipt's total and the items only matter for the split.

### Deployment
- "📷 Kassenbon scannen" in the expense form opens the camera; Tesseract.js (about 3 MB incl. German
  language data) is loaded from a CDN on first use and then cached by the browser.
- The server endpoint `/api/groups/{id}/parse-receipt` parses the text and adds a category suggestion.
- The photo is not stored anywhere; only the resulting expense is saved.
- Transparency: after a scan, "Erkannten Text anzeigen" shows what the phone read, and the app shows
  photo tips (flat, from above, good light, whole receipt).
- Next steps: collect more real receipts from other shops (locally, never in the repository) to
  measure the real accuracy; two receipts are not enough to judge the image settings. Item names are
  still taken as recognized and are sometimes garbled at the start of the line.
