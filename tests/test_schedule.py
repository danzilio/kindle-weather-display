"""Sleep scheduling: when the Kindle should wake next."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import server

NY = ZoneInfo("America/New_York")


@pytest.fixture
def cfg(monkeypatch):
    c = dict(server.DEFAULTS, refresh_minutes=30, quiet_start="23:00", quiet_end="06:00")
    monkeypatch.setattr(server, "CFG", c)
    return c


def at(h, m, day=12):
    return datetime(2026, 11, day, h, m, tzinfo=NY)


def mins(h, m):
    return h * 60 + m


@pytest.mark.parametrize("hm, quiet", [
    ((22, 59), False), ((23, 0), True), ((0, 0), True), ((5, 59), True), ((6, 0), False), ((12, 0), False),
])
def test_quiet_window_crossing_midnight(cfg, hm, quiet):
    assert server.in_quiet(mins(*hm)) is quiet


@pytest.mark.parametrize("hm, quiet", [
    ((12, 59), False), ((13, 0), True), ((13, 59), True), ((14, 0), False), ((0, 0), False),
])
def test_quiet_window_same_day(cfg, hm, quiet):
    cfg.update(quiet_start="13:00", quiet_end="14:00")
    assert server.in_quiet(mins(*hm)) is quiet


def test_equal_start_and_end_means_no_quiet_window(cfg):
    cfg.update(quiet_start="02:00", quiet_end="02:00")
    assert not any(server.in_quiet(m) for m in range(24 * 60))


@pytest.mark.parametrize("now, expected", [
    (at(10, 7), at(10, 30)),
    (at(10, 30), at(11, 0)),   # always strictly in the future
    (at(10, 59), at(11, 0)),
    (at(22, 15), at(22, 30)),
])
def test_next_wake_aligns_to_interval(cfg, now, expected):
    assert server.next_wake(now) == expected


def test_next_wake_skips_quiet_window_to_next_morning(cfg):
    assert server.next_wake(at(22, 45)) == at(6, 0, day=13)


def test_next_wake_during_quiet_window_after_midnight(cfg):
    assert server.next_wake(at(2, 10)) == at(6, 0)


def test_next_wake_interval_counts_from_midnight(cfg):
    cfg["refresh_minutes"] = 45
    assert server.next_wake(at(10, 7)) == at(10, 30)  # 14 × 45 min


def test_next_wake_with_no_quiet_window_runs_overnight(cfg):
    cfg.update(quiet_start="00:00", quiet_end="00:00")
    assert server.next_wake(at(23, 45)) == at(0, 0, day=13)
