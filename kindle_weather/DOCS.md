# Kindle Weather

Serves a 1072×1448, 16-level grayscale forecast image for a Kindle Paperwhite 3,
using data from the US National Weather Service (api.weather.gov — US locations only).

## Endpoints (port 8099)

- `/weather.png?battery=NN&charging=0|1` — the image. The Kindle passes its battery level, which is drawn in the footer.
- `/sleep` — seconds until the Kindle should wake next, aligned to `refresh_minutes` and skipping the quiet window.
- `/status` — JSON: last error, last battery report, data age.
- `/` — preview in a browser.

## Options

| Option | Meaning |
|---|---|
| `latitude`, `longitude` | Forecast point |
| `location_name` | Shown top-left |
| `refresh_minutes` | How often the Kindle wakes (10–180) |
| `quiet_start`, `quiet_end` | No wake-ups in this window (24h `HH:MM`; may cross midnight) |
| `temperature_entity` | Optional Home Assistant sensor for the big current temperature (°C or °F). If it's unavailable, the NWS observation is used and the screen says "Sensor offline". Leave empty to always use NWS. |
| `contact` | Optional email/URL added to the NWS User-Agent, as NWS requests |

## Home Assistant device

If an MQTT broker is available (e.g. the Mosquitto broker add-on with the MQTT integration
set up), the add-on registers a **Kindle Weather Display** device via MQTT discovery — no
configuration needed, the broker credentials come from the Supervisor. Entities:

| Entity | Meaning |
|---|---|
| Battery | Battery % from the Kindle's last check-in |
| Charging | Whether the Kindle was charging at its last check-in |
| Last check-in | When the Kindle last fetched the image |
| Next wake-up | When the Kindle is expected to check in next |

A check-in is any `/weather.png` request carrying `battery=`; the browser preview doesn't count.
Values are retained on the broker, so they survive Home Assistant and add-on restarts. The
entities go *unavailable* while the add-on is stopped. If the broker is installed after the
add-on, it's picked up within 5 minutes.

When no precipitation is forecast in the next 12 hours, the chart shows a temperature curve instead of precipitation bars.

Weather is fetched every 10 minutes in the background; if NWS is unreachable the last
good forecast keeps being served and the footer says "Offline" after 3 hours.
