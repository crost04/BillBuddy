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
| Phase | What we did / decided |
|-------|-----------------------|
| Business Understanding | _TBD_ |
| Data Understanding | _TBD_ |
| Data Preparation | _TBD_ |
| Modeling | _TBD_ |
| Evaluation | _TBD_ |
| Deployment | _TBD_ |

## 3. Recurring-cost detection (`ml/recurring`)
| Phase | What we did / decided |
|-------|-----------------------|
| Business Understanding | _TBD_ |
| Data Understanding | _TBD_ |
| Data Preparation | _TBD_ |
| Modeling | _TBD_ |
| Evaluation | _TBD_ |
| Deployment | _TBD_ |

## 4. Anomaly detection (`ml/anomaly`)
| Phase | What we did / decided |
|-------|-----------------------|
| Business Understanding | _TBD_ |
| Data Understanding | _TBD_ |
| Data Preparation | _TBD_ |
| Modeling | _TBD_ |
| Evaluation | _TBD_ |
| Deployment | _TBD_ |

## 5. Receipt scan (`ml/receipt_ocr`)
| Phase | What we did / decided |
|-------|-----------------------|
| Business Understanding | _TBD_ |
| Data Understanding | _TBD_ |
| Data Preparation | _TBD_ |
| Modeling | _TBD_ |
| Evaluation | _TBD_ |
| Deployment | _TBD_ |
