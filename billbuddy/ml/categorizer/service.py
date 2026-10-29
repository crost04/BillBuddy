"""Category suggestions for the app.

Every group gets its own model, trained on the sample data plus the group's
own categorized expenses. Models live only in memory: training takes a fraction
of a second, and no personal data is written to disk. A model is retrained as
soon as the group's categorized expenses change, so every correction counts.
"""

import threading
from collections import OrderedDict

from sqlalchemy.orm import Session

from billbuddy.ml.categorizer.model import CategoryModel, Suggestion
from billbuddy.ml.categorizer.training_data import group_data, sample_data

MAX_CACHED_MODELS = 50

# group_id -> (fingerprint of the group's training data, model)
_models: OrderedDict[int, tuple[int, CategoryModel]] = OrderedDict()
_lock = threading.Lock()


def suggest(session: Session, group_id: int, description: str, amount: float) -> Suggestion | None:
    return model_for_group(session, group_id).suggest(description, amount)


def model_for_group(session: Session, group_id: int) -> CategoryModel:
    own = group_data(session, group_id)
    fingerprint = hash((tuple(own.descriptions), tuple(own.amounts), tuple(own.categories)))

    with _lock:
        cached = _models.get(group_id)
        if cached and cached[0] == fingerprint:
            _models.move_to_end(group_id)
            return cached[1]

        data = sample_data() + own
        model = CategoryModel.train(data.descriptions, data.amounts, data.categories, data.weights)
        _models[group_id] = (fingerprint, model)
        # Keep memory small: forget the models of groups that were not used for a while
        while len(_models) > MAX_CACHED_MODELS:
            _models.popitem(last=False)
        return model
