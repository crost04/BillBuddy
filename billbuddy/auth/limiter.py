"""Protection against password guessing: block an email address after too many failed logins."""

import datetime as dt
from collections import defaultdict

from billbuddy.auth.service import normalize_email


class TooManyAttemptsError(Exception):
    """Too many failed logins for this email address in a short time."""


class LoginLimiter:
    """Counts failed logins per email address in memory.

    Memory is enough here: the app runs as a single server process, and a
    restart only resets the counters.
    """

    def __init__(self, max_failures: int = 10, window: dt.timedelta = dt.timedelta(minutes=15)):
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[str, list[dt.datetime]] = defaultdict(list)

    def check(self, email: str) -> None:
        key = normalize_email(email)
        cutoff = dt.datetime.now() - self.window
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        if len(self._failures[key]) >= self.max_failures:
            raise TooManyAttemptsError("Too many failed logins, please try again in 15 minutes")

    def record_failure(self, email: str) -> None:
        self._failures[normalize_email(email)].append(dt.datetime.now())

    def reset(self, email: str) -> None:
        self._failures.pop(normalize_email(email), None)
