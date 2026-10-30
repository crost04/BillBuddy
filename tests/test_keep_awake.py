"""Tests for the self-ping that keeps the free Render server awake (billbuddy.api.keep_awake)."""

import threading

from billbuddy.api import keep_awake


def test_not_active_outside_render(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert keep_awake.start(threading.Event()) is None


def test_calls_the_health_endpoint_until_stopped(monkeypatch):
    called = []
    stop = threading.Event()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"{}"

    def fake_urlopen(url, timeout):
        called.append(url)
        if len(called) == 2:
            stop.set()
        return Response()

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://billbuddy.example/")
    monkeypatch.setattr(keep_awake, "INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(keep_awake.urllib.request, "urlopen", fake_urlopen)

    thread = keep_awake.start(stop)
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert called == ["https://billbuddy.example/api/health"] * 2


def test_network_errors_do_not_stop_it(monkeypatch):
    attempts = []
    stop = threading.Event()

    def failing_urlopen(url, timeout):
        attempts.append(url)
        if len(attempts) == 3:
            stop.set()
        raise OSError("no network")

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://billbuddy.example")
    monkeypatch.setattr(keep_awake, "INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(keep_awake.urllib.request, "urlopen", failing_urlopen)

    keep_awake.start(stop).join(timeout=5)

    assert len(attempts) == 3
