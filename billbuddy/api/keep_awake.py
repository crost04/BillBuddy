"""Keeps the free Render server awake while it runs.

Render stops free web services after 15 minutes without incoming requests,
and waking up takes about a minute. The scheduled GitHub workflow that was
meant to prevent this ran only every few hours (GitHub delays schedules of
small repositories). So the app now calls its own public address every
10 minutes. The request comes in through Render's front door like any
visitor's, which counts as activity.

Only active on Render, which sets RENDER_EXTERNAL_URL automatically. One
service running all month needs about 744 of the 750 free instance hours.
"""

import logging
import os
import threading
import urllib.request

INTERVAL_SECONDS = 10 * 60
log = logging.getLogger(__name__)


def start(stop: threading.Event) -> threading.Thread | None:
    """Start pinging in the background until `stop` is set; None when not on Render."""
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not base_url:
        return None
    url = f"{base_url.rstrip('/')}/api/health"
    thread = threading.Thread(target=_ping_until, args=(url, stop), name="keep-awake", daemon=True)
    thread.start()
    return thread


def _ping_until(url: str, stop: threading.Event) -> None:
    while not stop.wait(INTERVAL_SECONDS):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                response.read()
        except OSError as error:  # network trouble: try again next time
            log.warning("Keep-awake request failed: %s", error)
