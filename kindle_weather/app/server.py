"""Tiny HTTP server: serves the Kindle weather PNG and tells the Kindle how long to sleep."""
import io
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

import render
from ha_mqtt import KindleMQTT
from weather import NWS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kindle-weather")


def load_config():
    defaults = {
        "latitude": 42.3876, "longitude": -71.0995, "location_name": "Somerville",
        "refresh_minutes": 30, "quiet_start": "23:00", "quiet_end": "06:00",
        "contact": "", "port": 8099, "temperature_entity": "",
    }
    path = os.environ.get("OPTIONS", "/data/options.json")
    if os.path.exists(path):
        with open(path) as f:
            defaults.update({k: v for k, v in json.load(f).items() if v not in (None, "")})
    return defaults


CFG = load_config()
UA = f"kindle-weather-display ({CFG['contact'] or 'home-assistant add-on'})"
nws = NWS(float(CFG["latitude"]), float(CFG["longitude"]), UA)
state = {"data": None, "error": None, "battery": None, "charging": False, "last_seen": None}
lock = threading.Lock()


def refresher():
    while True:
        try:
            d = nws.fetch()
            with lock:
                state["data"], state["error"] = d, None
            log.info("weather updated (station %s)", d["station"])
            time.sleep(600)
        except Exception as e:  # keep serving the last good data
            with lock:
                state["error"] = str(e)
            log.warning("weather fetch failed: %s", e)
            time.sleep(120)


def tz():
    d = state["data"]
    return ZoneInfo((d or {}).get("tz") or "America/New_York")


def _hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def in_quiet(minute_of_day):
    qs, qe = _hm(CFG["quiet_start"]), _hm(CFG["quiet_end"])
    if qs == qe:
        return False
    return qs <= minute_of_day < qe if qs < qe else (minute_of_day >= qs or minute_of_day < qe)


def next_wake(now):
    """Next refresh time: aligned to the refresh interval, skipping the quiet window."""
    step = max(5, int(CFG["refresh_minutes"]))
    mid = now.replace(hour=0, minute=0, second=0, microsecond=0)
    mins = (now - mid).total_seconds() / 60
    cand = mid + timedelta(minutes=(int(mins // step) + 1) * step)
    for _ in range(24 * 60 // step + 2):
        if not in_quiet(cand.hour * 60 + cand.minute):
            return cand
        cand += timedelta(minutes=step)
    return now + timedelta(minutes=step)


HA_API = os.environ.get("HA_API", "http://supervisor/core/api")
VERSION = os.environ.get("ADDON_VERSION") or None
ha_device = KindleMQTT(version=VERSION)


def read_entity_temp():
    """Return (fahrenheit, failed). (None, False) when no entity is configured."""
    ent = (CFG.get("temperature_entity") or "").strip()
    if not ent:
        return None, False
    try:
        req = urllib.request.Request(f"{HA_API}/states/{ent}", headers={
            "Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}",
            "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            st = json.load(r)
        v = float(st["state"])  # 'unavailable' / 'unknown' raise here
        unit = (st.get("attributes") or {}).get("unit_of_measurement", "°F")
        if "C" in unit:
            v = v * 9 / 5 + 32
        return v, False
    except Exception as e:
        log.warning("temperature entity %s unavailable: %s", ent, e)
        return None, True


def make_png(battery, charging):
    with lock:
        data, err = state["data"], state["error"]
    if data is None:
        raise RuntimeError(err or "no weather data yet")
    z = tz()
    now = datetime.now(z)
    loc = LocationInfo("", "", str(z), float(CFG["latitude"]), float(CFG["longitude"]))
    s = sun(loc.observer, date=now.date(), tzinfo=z)
    stale = time.time() - data["fetched_at"] > 3 * 3600
    local, failed = read_entity_temp()
    img = render.render(data, CFG["location_name"], now=now, battery=battery, charging=charging,
                        next_update=next_wake(now), sun=(s["sunrise"], s["sunset"]), stale=stale,
                        local_temp=local, local_failed=failed, version=VERSION)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/weather.png", "/kindle.png"):
                bat = q.get("battery", [None])[0]
                bat = int(float(bat)) if bat not in (None, "") else None
                chg = q.get("charging", ["0"])[0] in ("1", "true", "yes")
                if bat is not None:  # a Kindle check-in (the browser preview sends no battery)
                    with lock:
                        state.update(battery=bat, charging=chg, last_seen=time.time())
                    now = datetime.now(tz())
                    ha_device.checkin(bat, chg, now, next_wake(now))
                self._send(200, make_png(bat, chg), "image/png")
            elif u.path == "/sleep":
                now = datetime.now(tz())
                secs = max(60, int((next_wake(now) - now).total_seconds()))
                self._send(200, f"{secs}\n".encode(), "text/plain")
            elif u.path == "/status":
                with lock:
                    s = {k: state[k] for k in ("error", "battery", "charging", "last_seen")}
                    s["data_age_s"] = int(time.time() - state["data"]["fetched_at"]) if state["data"] else None
                self._send(200, json.dumps(s).encode(), "application/json")
            elif u.path == "/":
                html = (b"<html><body style='margin:0;background:#888'>"
                        b"<img src='/weather.png' style='height:100vh;display:block;margin:auto'></body></html>")
                self._send(200, html, "text/html")
            else:
                self._send(404, b"not found\n", "text/plain")
        except Exception as e:
            log.exception("request failed")
            self._send(503, f"{e}\n".encode(), "text/plain")

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    threading.Thread(target=refresher, daemon=True).start()
    ha_device.start()
    port = int(CFG.get("port", 8099))
    log.info("listening on :%d for %s", port, CFG["location_name"])
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
