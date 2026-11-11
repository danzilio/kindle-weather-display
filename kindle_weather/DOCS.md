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

When no precipitation is forecast in the next 12 hours, the chart shows a temperature curve instead of precipitation bars.

Weather is fetched every 10 minutes in the background; if NWS is unreachable the last
good forecast keeps being served and the footer says "Offline" after 3 hours.
