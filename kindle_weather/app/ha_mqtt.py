"""Publish the Kindle as a Home Assistant device over MQTT discovery.

Broker credentials come from the Supervisor (`services: mqtt:want` in config.yaml), so a
running Mosquitto add-on is picked up with no configuration. Without a broker this is a no-op.
"""
import json
import logging
import os
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

log = logging.getLogger("kindle-weather.mqtt")

PREFIX = "homeassistant"
NODE = "kindle_weather"
STATE_TOPIC = f"{NODE}/state"
AVAIL_TOPIC = f"{NODE}/availability"


def _device(version):
    d = {"identifiers": [NODE], "name": "Kindle Weather Display",
         "manufacturer": "Amazon", "model": "Kindle Paperwhite (7th gen)"}
    if version:
        d["sw_version"] = version
    return d


def discovery_configs(version):
    """(topic, payload) pairs for every entity on the Kindle device."""
    base = {"state_topic": STATE_TOPIC, "availability_topic": AVAIL_TOPIC, "device": _device(version)}
    ents = [
        ("sensor", "battery", {"name": "Battery", "device_class": "battery", "unit_of_measurement": "%",
                               "state_class": "measurement", "value_template": "{{ value_json.battery }}"}),
        ("binary_sensor", "charging", {"name": "Charging", "device_class": "battery_charging",
                                       "value_template": "{{ 'ON' if value_json.charging else 'OFF' }}"}),
        ("sensor", "last_checkin", {"name": "Last check-in", "device_class": "timestamp",
                                    "value_template": "{{ value_json.last_checkin }}"}),
        ("sensor", "next_wake", {"name": "Next wake-up", "device_class": "timestamp",
                                 "value_template": "{{ value_json.next_wake }}"}),
    ]
    out = []
    for component, key, cfg in ents:
        payload = {**base, **cfg, "unique_id": f"{NODE}_{key}"}
        out.append((f"{PREFIX}/{component}/{NODE}/{key}/config", payload))
    return out


def supervisor_mqtt():
    """Broker details from the Supervisor, or None if there's no MQTT service."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request("http://supervisor/services/mqtt",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r).get("data") or None
    except Exception as e:
        log.info("no MQTT service from Supervisor (%s)", e)
        return None


class KindleMQTT:
    def __init__(self, version=None, get_broker=supervisor_mqtt, retry_s=300):
        self.version = version
        self._get_broker = get_broker
        self._retry_s = retry_s
        self._client = None
        self._last = None  # last state payload, re-sent on reconnect
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._connect_loop, daemon=True, name="mqtt").start()

    def _connect_loop(self):
        while True:
            broker = self._get_broker()
            if broker:
                try:
                    self._connect(broker)
                    return
                except Exception as e:
                    log.warning("MQTT connect to %s failed: %s", broker.get("host"), e)
            else:
                log.info("Home Assistant device disabled until an MQTT broker is available; retrying in %ds",
                         self._retry_s)
            time.sleep(self._retry_s)

    def _connect(self, b):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{NODE}_addon")
        if b.get("username"):
            c.username_pw_set(b["username"], b.get("password"))
        if b.get("ssl"):
            c.tls_set()
        c.will_set(AVAIL_TOPIC, "offline", retain=True)
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        c.reconnect_delay_set(1, 120)
        c.connect(b["host"], int(b.get("port", 1883)))
        c.loop_start()  # handles reconnects from here on
        self._client = c

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.warning("MQTT connection refused: %s", reason_code)
            return
        log.info("connected to MQTT; publishing Kindle device to Home Assistant")
        client.subscribe(f"{PREFIX}/status")
        self._announce(client)

    def _on_message(self, client, userdata, msg):
        # Home Assistant restarted: re-send discovery and the latest state
        if msg.topic == f"{PREFIX}/status" and msg.payload == b"online":
            self._announce(client)

    def _announce(self, client):
        for topic, payload in discovery_configs(self.version):
            client.publish(topic, json.dumps(payload), retain=True)
        client.publish(AVAIL_TOPIC, "online", retain=True)
        with self._lock:
            last = self._last
        if last:
            client.publish(STATE_TOPIC, last, retain=True)

    def checkin(self, battery, charging, when, next_wake):
        """Record a Kindle check-in. `when` and `next_wake` are aware datetimes."""
        payload = json.dumps({"battery": battery, "charging": bool(charging),
                              "last_checkin": when.isoformat(timespec="seconds"),
                              "next_wake": next_wake.isoformat(timespec="seconds")})
        with self._lock:
            self._last = payload
        if self._client is not None:
            self._client.publish(STATE_TOPIC, payload, retain=True)
