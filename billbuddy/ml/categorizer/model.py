"""The categorization model.

Feature: the cleaned description, split into overlapping groups of 2–5
characters ("rewe" -> "re", "ew", "we", "rew", ...) and weighted with TF-IDF.
Character groups still work with typos and unknown spellings ("Rewe-Markt").

The amount was tested as a second feature but brought no measurable benefit on
the sample data (see docs/categorizer-report.md), so the simpler text-only
model is used. use_amount=True keeps the option to re-test it with real data.

Classifier: logistic regression. It is fast, works well with little data and
returns a probability per category, which is used as the confidence.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from billbuddy.ml.categorizer.preprocessing import clean_description

# Below this probability the app makes no suggestion. Chosen in the evaluation:
# a wrong suggestion is worse than none, especially for shops the model never saw.
MIN_CONFIDENCE = 0.7


def build_pipeline(use_amount: bool = False, c: float = 10.0) -> Pipeline:
    features = [
        ("text", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True), "text"),
    ]
    if use_amount:
        log_amount = Pipeline([("log", FunctionTransformer(np.log1p)), ("scale", StandardScaler())])
        features.append(("amount", log_amount, ["amount"]))
    return Pipeline([
        ("features", ColumnTransformer(features)),
        # class_weight="balanced": rare categories (e.g. Travel) count as much as frequent ones
        ("classifier", LogisticRegression(C=c, class_weight="balanced", max_iter=2000)),
    ])


def to_frame(descriptions, amounts) -> pd.DataFrame:
    return pd.DataFrame({
        "text": [clean_description(d) for d in descriptions],
        "amount": [float(a) for a in amounts],
    })


@dataclass
class Suggestion:
    category: str
    confidence: float  # probability between 0 and 1


class CategoryModel:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline

    @classmethod
    def train(cls, descriptions, amounts, categories, weights=None) -> "CategoryModel":
        pipeline = build_pipeline()
        fit_params = {} if weights is None else {"classifier__sample_weight": np.asarray(weights)}
        pipeline.fit(to_frame(descriptions, amounts), list(categories), **fit_params)
        return cls(pipeline)

    def suggest(self, description: str, amount: float) -> Suggestion | None:
        """The most likely category, or None if the model is not sure enough."""
        frame = to_frame([description], [amount])
        if not frame.text[0]:
            return None
        probabilities = self.pipeline.predict_proba(frame)[0]
        best = int(probabilities.argmax())
        if probabilities[best] < MIN_CONFIDENCE:
            return None
        return Suggestion(str(self.pipeline.classes_[best]), float(probabilities[best]))
