"""The current date in the users' time zone (the server itself may run in UTC)."""

import datetime as dt
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Berlin")


def today() -> dt.date:
    return dt.datetime.now(TIMEZONE).date()
