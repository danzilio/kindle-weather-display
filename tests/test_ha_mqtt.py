"""MQTT discovery publisher for the Home Assistant device."""
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import ha_mqtt
from ha_mqtt import AVAIL_TOPIC, STATE_TOPIC, KindleMQTT, discovery_configs

NY = ZoneInfo("America/New_York")
WHEN = datetime(2026, 11, 12, 10, 3, 21, tzinfo=NY)
NEXT = datetime(2026, 11, 12, 10, 30, tzinfo=NY)


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def topics(self):
        return [t for t, _, _ in self.published]


def rc(failure):
    return SimpleNamespace(is_failure=failure)


def test_discovery_configs():
    cfgs = discovery_configs("0.4.0")
    payloads = {p["unique_id"]: (t, p) for t, p in cfgs}
    assert set(payloads) == {"kindle_weather_battery", "kindle_weather_charging",
                             "kindle_weather_last_checkin", "kindle_weather_next_wake"}
    assert payloads["kindle_weather_battery"][1]["device_class"] == "battery"
    assert payloads["kindle_weather_battery"][1]["unit_of_measurement"] == "%"
    assert payloads["kindle_weather_charging"][0] == "homeassistant/binary_sensor/kindle_weather/charging/config"
    assert payloads["kindle_weather_charging"][1]["device_class"] == "battery_charging"
    assert payloads["kindle_weather_last_checkin"][1]["device_class"] == "timestamp"
    assert payloads["kindle_weather_next_wake"][1]["device_class"] == "timestamp"
    for topic, p in cfgs:
        assert topic.startswith("homeassistant/") and topic.endswith("/config")
        assert p["state_topic"] == STATE_TOPIC and p["availability_topic"] == AVAIL_TOPIC
        assert p["device"]["identifiers"] == ["kindle_weather"]
        assert p["device"]["sw_version"] == "0.4.0"
        json.dumps(p)  # must be serialisable


def test_discovery_without_version_omits_sw_version():
    assert all("sw_version" not in p["device"] for _, p in discovery_configs(None))


def test_charging_template_renders_on_off():
    [tmpl] = [p["value_template"] for _, p in discovery_configs(None) if p["unique_id"].endswith("charging")]
    assert "'ON' if value_json.charging else 'OFF'" in tmpl


def test_checkin_before_connect_is_kept():
    m = KindleMQTT()
    m.checkin(73, 1, WHEN, NEXT)  # no client yet: must not raise
    assert json.loads(m._last) == {"battery": 73, "charging": True,
                                   "last_checkin": "2026-11-12T10:03:21-05:00",
                                   "next_wake": "2026-11-12T10:30:00-05:00"}


def test_checkin_publishes_retained_state():
    m, c = KindleMQTT(), FakeClient()
    m._client = c
    m.checkin(50, False, WHEN, NEXT)
    [(topic, payload, retain)] = c.published
    assert topic == STATE_TOPIC and retain
    assert json.loads(payload)["charging"] is False


def test_connect_announces_discovery_availability_and_last_state():
    m, c = KindleMQTT(version="0.4.0"), FakeClient()
    m.checkin(73, True, WHEN, NEXT)
    m._on_connect(c, None, None, rc(False), None)
    assert c.subscribed == ["homeassistant/status"]
    topics = c.topics()
    assert topics[:4] == [t for t, _ in discovery_configs("0.4.0")]
    assert topics[4:] == [AVAIL_TOPIC, STATE_TOPIC]
    assert all(retain for _, _, retain in c.published)
    assert c.published[4][1] == "online"


def test_connect_without_state_sends_no_state():
    m, c = KindleMQTT(), FakeClient()
    m._on_connect(c, None, None, rc(False), None)
    assert STATE_TOPIC not in c.topics()


def test_refused_connection_publishes_nothing():
    m, c = KindleMQTT(), FakeClient()
    m._on_connect(c, None, None, rc(True), None)
    assert c.published == [] and c.subscribed == []


@pytest.mark.parametrize("payload, announces", [(b"online", True), (b"offline", False)])
def test_home_assistant_restart_reannounces(payload, announces):
    m, c = KindleMQTT(), FakeClient()
    m.checkin(73, True, WHEN, NEXT)
    m._on_message(c, None, SimpleNamespace(topic="homeassistant/status", payload=payload))
    assert (STATE_TOPIC in c.topics()) is announces


def test_supervisor_lookup_without_token(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert ha_mqtt.supervisor_mqtt() is None
