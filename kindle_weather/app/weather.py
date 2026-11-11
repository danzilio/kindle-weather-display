"""Fetch forecast data from the US National Weather Service API (api.weather.gov)."""
import json
import time
import urllib.request

API = "https://api.weather.gov"


def _get(url, ua, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class NWS:
    def __init__(self, lat, lon, user_agent):
        self.lat, self.lon, self.ua = lat, lon, user_agent
        self._points = None
        self._station = None

    def _resolve(self):
        if self._points is None:
            p = _get(f"{API}/points/{self.lat:.4f},{self.lon:.4f}", self.ua)["properties"]
            self._points = p
        if self._station is None:
            st = _get(self._points["observationStations"], self.ua)
            self._station = st["features"][0]["properties"]["stationIdentifier"]
        return self._points

    def fetch(self):
        p = self._resolve()
        daily = _get(p["forecast"], self.ua)["properties"]["periods"]
        hourly = _get(p["forecastHourly"], self.ua)["properties"]["periods"][:24]
        try:
            obs = _get(f"{API}/stations/{self._station}/observations/latest", self.ua)["properties"]
        except Exception:
            obs = {}
        keep = lambda d, ks: {k: d.get(k) for k in ks}
        return {
            "station": self._station,
            "tz": p.get("timeZone", "America/New_York"),
            "fetched_at": time.time(),
            "daily": [keep(x, ["name", "startTime", "isDaytime", "temperature",
                               "probabilityOfPrecipitation", "shortForecast", "icon"]) for x in daily],
            "hourly": [keep(x, ["startTime", "temperature", "probabilityOfPrecipitation",
                                "shortForecast", "isDaytime", "icon"]) for x in hourly],
            "obs": keep(obs, ["timestamp", "textDescription", "temperature", "relativeHumidity",
                              "windSpeed", "windDirection", "heatIndex", "windChill", "icon"]),
        }
