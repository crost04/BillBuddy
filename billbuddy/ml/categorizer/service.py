"""Category suggestions for the app.

Every group gets its own model, trained on the sample data plus the group's
own categorized expenses. Models live only in memory, and no personal data is
written to disk.

Speed: on the small free server, training takes a few seconds. So a request
never waits for training: when the group's data has changed, the previous model
answers right away while the new one is trained in a background thread. The base
model (sample data only) is trained once when the server starts. A group is
retrained at most once a minute, so entering several expenses in a row does not
keep the small server busy.
"""

import threading
import time
from collections import OrderedDict

from sqlalchemy.orm import Session

from billbuddy.ml.categorizer.model import CategoryModel, Suggestion
from billbuddy.ml.categorizer.training_data import TrainingData, group_data, sample_data

MAX_CACHED_MODELS = 50
MIN_SECONDS_BETWEEN_TRAININGS = 60
# Tests switch this off to get deterministic results
TRAIN_IN_BACKGROUND = True

# group_id -> (fingerprint of the group's training data, model)
_models: OrderedDict[int, tuple[int, CategoryModel]] = OrderedDict()
_training: dict[int, threading.Thread] = {}
_last_training: dict[int, float] = {}  # group_id -> time.monotonic() of the last start
_base_model: CategoryModel | None = None
_lock = threading.Lock()
_base_lock = threading.Lock()  # separate, so cached models are served while the base model trains


def suggest(session: Session, group_id: int, description: str, amount: float) -> Suggestion | None:
    return model_for_group(session, group_id).suggest(description, amount)


def warm_up() -> None:
    """Train the base model ahead of time (called in the background at server start)."""
    base_model()


def base_model() -> CategoryModel:
    global _base_model
    with _base_lock:
        if _base_model is None:
            data = sample_data()
            _base_model = CategoryModel.train(data.descriptions, data.amounts, data.categories, data.weights)
        return _base_model


def model_for_group(session: Session, group_id: int) -> CategoryModel:
    own = group_data(session, group_id)
    if len(own) == 0:
        return base_model()
    fingerprint = hash((tuple(own.descriptions), tuple(own.amounts), tuple(own.categories)))

    with _lock:
        cached = _models.get(group_id)
        if cached and cached[0] == fingerprint:
            _models.move_to_end(group_id)
            return cached[1]
        already_training = group_id in _training
        recently_trained = time.monotonic() - _last_training.get(group_id, -1e9) < MIN_SECONDS_BETWEEN_TRAININGS

    if not TRAIN_IN_BACKGROUND:
        return _train(group_id, fingerprint, own)
    # A group without a model is trained at once; otherwise at most once a minute
    if not already_training and (cached is None or not recently_trained):
        thread = threading.Thread(target=_train, args=(group_id, fingerprint, own), daemon=True)
        with _lock:
            _training[group_id] = thread
            _last_training[group_id] = time.monotonic()
        thread.start()
    # Until the new model is ready: the group's previous model, or the base model
    return cached[1] if cached else base_model()


def wait_for_training(group_id: int) -> None:
    """For tests: block until a background training of the group has finished."""
    thread = _training.get(group_id)
    if thread:
        thread.join()


def _train(group_id: int, fingerprint: int, own: TrainingData) -> CategoryModel:
    try:
        data = sample_data() + own
        model = CategoryModel.train(data.descriptions, data.amounts, data.categories, data.weights)
        with _lock:
            _models[group_id] = (fingerprint, model)
            _models.move_to_end(group_id)
            # Keep memory small: forget the models of groups that were not used for a while
            while len(_models) > MAX_CACHED_MODELS:
                _models.popitem(last=False)
        return model
    finally:
        with _lock:
            _training.pop(group_id, None)
