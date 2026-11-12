"""/weather.png check-ins: battery/charging parsing and publishing to Home Assistant."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import server


class FakeDevice:
    def __init__(self):
        self.checkins = []

    def checkin(self, battery, charging, when, next_wake):
        self.checkins.append((battery, charging, when, next_wake))


@pytest.fixture
def app(monkeypatch):
    device = FakeDevice()
    server.configure(dict(server.DEFAULTS), device=device)
    monkeypatch.setattr(server, "state",
                        {"data": None, "error": None, "battery": None, "charging": False, "last_seen": None})
    monkeypatch.setattr(server, "make_png", lambda battery, charging: b"PNG")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, r.read()

    yield get, device
    httpd.shutdown()
    httpd.server_close()


def test_checkin_is_published(app):
    get, device = app
    assert get("/weather.png?battery=73&charging=1") == (200, b"PNG")
    [(battery, charging, when, nxt)] = device.checkins
    assert (battery, charging) == (73, True)
    assert nxt > when
    assert nxt == server.next_wake(when)


def test_checkin_updates_status(app):
    get, _ = app
    get("/weather.png?battery=41.6&charging=0")
    status = json.loads(get("/status")[1])
    assert status["battery"] == 41 and status["charging"] is False and status["last_seen"]


def test_preview_without_battery_is_not_a_checkin(app):
    get, device = app
    assert get("/weather.png")[0] == 200
    assert device.checkins == []
    assert json.loads(get("/status")[1])["last_seen"] is None


@pytest.mark.parametrize("raw", ["", "abc", "nan", "inf"])
def test_bad_battery_still_serves_image_but_is_ignored(app, raw):
    get, device = app
    assert get(f"/weather.png?battery={raw}") == (200, b"PNG")
    assert device.checkins == []


@pytest.mark.parametrize("raw, expected", [
    ("1", True), ("true", True), ("yes", True), ("0", False), ("false", False), (None, False),
])
def test_charging_flag(app, raw, expected):
    get, device = app
    get("/weather.png?battery=50" + (f"&charging={raw}" if raw is not None else ""))
    assert device.checkins[-1][1] is expected


@pytest.mark.parametrize("raw, expected", [
    ("73", 73), ("73.9", 73), ("0", 0), ("100", 100), (None, None), ("", None), ("x", None),
])
def test_parse_battery(raw, expected):
    assert server.parse_battery(raw) == expected
