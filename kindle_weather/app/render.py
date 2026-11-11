"""Render NWS weather data to a 16-level grayscale PNG for a Kindle Paperwhite (1072x1448)."""
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

W, H = 1072, 1448
S = 2  # supersampling factor; drawn at 2x then downsampled for smooth edges
BLACK, DARK, MID, LIGHT, WHITE = 0, 68, 136, 204, 255
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONTS = {
    "regular": "Inter-Regular.otf",
    "medium": "Inter-Medium.otf",
    "semibold": "Inter-SemiBold.otf",
    "bold": "Inter-Bold.otf",
    "display": "InterDisplay-Light.otf",
    "display-semi": "InterDisplay-SemiBold.otf",
}
_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(os.path.join(FONT_DIR, FONTS[weight]), size * S)
    return _font_cache[key]


class Canvas:
    """Thin wrapper so all drawing code uses 1x coordinates."""

    def __init__(self):
        self.img = Image.new("L", (W * S, H * S), WHITE)
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        return [(x * S, y * S) for x, y in pts]

    def text(self, xy, s, size, weight="regular", fill=BLACK, anchor="la"):
        self.d.text((xy[0] * S, xy[1] * S), s, font=font(weight, size), fill=fill, anchor=anchor)

    def textlen(self, s, size, weight="regular"):
        return self.d.textlength(s, font=font(weight, size)) / S

    def line(self, pts, fill=BLACK, width=2):
        self.d.line(self._p(pts), fill=fill, width=int(width * S), joint="curve")

    def rect(self, box, fill=None, outline=None, width=2, radius=0):
        b = [v * S for v in box]
        if radius:
            self.d.rounded_rectangle(b, radius=radius * S, fill=fill, outline=outline, width=int(width * S))
        else:
            self.d.rectangle(b, fill=fill, outline=outline, width=int(width * S))

    def circle(self, cx, cy, r, fill=None, outline=None, width=2):
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                       fill=fill, outline=outline, width=int(width * S))

    def polygon(self, pts, fill=BLACK):
        self.d.polygon(self._p(pts), fill=fill)

    def finish(self):
        img = self.img.resize((W, H), Image.LANCZOS)
        # snap to the Kindle's 16 gray levels so the panel doesn't dither
        return img.point(lambda v: min(255, int(round(v / 17.0)) * 17))


# ---------------------------------------------------------------- icons

def icon_kind(url):
    """Map an api.weather.gov icon URL to (kind, is_night)."""
    if not url:
        return "cloudy", False
    path = url.split("?")[0]
    night = "/night/" in path
    code = path.rsplit("/", 1)[-1].split(",")[0]
    if code.startswith("wind_"):
        code = code[5:]
    table = {
        "skc": "clear", "few": "clear", "hot": "clear", "cold": "clear",
        "sct": "partly", "bkn": "mostly", "ovc": "cloudy",
        "rain": "rain", "rain_showers": "rain", "rain_showers_hi": "rain",
        "tsra": "thunder", "tsra_sct": "thunder", "tsra_hi": "thunder",
        "tornado": "thunder", "hurricane": "thunder", "tropical_storm": "thunder",
        "snow": "snow", "blizzard": "snow",
        "rain_snow": "mix", "rain_sleet": "mix", "snow_sleet": "mix", "sleet": "mix",
        "fzra": "mix", "rain_fzra": "mix", "snow_fzra": "mix",
        "fog": "fog", "haze": "fog", "smoke": "fog", "dust": "fog",
    }
    return table.get(code, "cloudy"), night


def _sun(c, cx, cy, r, stroke):
    c.circle(cx, cy, r * 0.45, outline=BLACK, width=stroke)
    for i in range(8):
        a = i * math.pi / 4
        c.line([(cx + math.cos(a) * r * 0.65, cy + math.sin(a) * r * 0.65),
                (cx + math.cos(a) * r * 0.92, cy + math.sin(a) * r * 0.92)], width=stroke)


def _moon(c, cx, cy, r, stroke):
    c.circle(cx, cy, r * 0.6, fill=BLACK)
    c.circle(cx + r * 0.3, cy - r * 0.22, r * 0.52, fill=WHITE)


def _cloud(c, cx, cy, w, stroke, fill=WHITE):
    """Cloud centred on (cx, cy), w wide. Drawn as black shape, then inset white."""
    h = w * 0.5
    parts = lambda t: [
        ("c", cx - w * 0.22, cy + h * 0.08, w * 0.22 - t),
        ("c", cx + w * 0.05, cy - h * 0.18, w * 0.30 - t),
        ("c", cx + w * 0.28, cy + h * 0.12, w * 0.20 - t),
        ("r", cx - w * 0.22, cy + h * 0.08, cx + w * 0.28, cy + h * 0.12 + w * 0.20 - t),
        ("r", cx - w * 0.44 + t, cy + h * 0.08, cx + w * 0.48 - t, cy + h * 0.32 - t),
    ]
    for col, t in ((BLACK, 0), (fill, stroke)):
        for p in parts(t):
            if p[0] == "c":
                c.circle(p[1], p[2], p[3], fill=col)
            else:
                c.rect((p[1], p[2], p[3], p[4]), fill=col)
        if col == BLACK:
            # rounded bottom corners
            pass


def draw_icon(c, cx, cy, size, kind, night=False):
    """Draw a weather icon in a size x size box centred on (cx, cy)."""
    st = max(3, size / 22)
    r = size / 2
    if kind == "clear":
        (_moon if night else _sun)(c, cx, cy, r, st)
        return
    if kind in ("partly", "mostly"):
        (_moon if night else _sun)(c, cx + r * 0.28, cy - r * 0.3, r * 0.62, st * 0.9)
        _cloud(c, cx - r * 0.08, cy + r * 0.12, size * (0.72 if kind == "partly" else 0.86), st)
        return
    if kind == "fog":
        _cloud(c, cx, cy - r * 0.2, size * 0.8, st)
        for i, (a, b) in enumerate(((-0.45, 0.35), (-0.3, 0.5), (-0.5, 0.2))):
            y = cy + r * (0.38 + i * 0.2)
            c.line([(cx + r * a, y), (cx + r * b, y)], width=st)
        return
    # cloud-based icons with precipitation underneath
    cloud_y = cy - (r * 0.22 if kind != "cloudy" else 0)
    _cloud(c, cx, cloud_y, size * 0.9, st)
    base = cloud_y + size * 0.9 * 0.5 * 0.32 + st * 2
    if kind == "rain":
        for dx in (-0.3, 0.0, 0.3):
            x = cx + r * dx
            c.line([(x + r * 0.08, base), (x - r * 0.06, base + r * 0.38)], width=st)
    elif kind == "snow":
        for dx, dy in ((-0.3, 0.12), (0.0, 0.3), (0.3, 0.12)):
            _flake(c, cx + r * dx, base + r * dy, r * 0.11, st * 0.7)
    elif kind == "mix":
        c.line([(cx - r * 0.22, base), (cx - r * 0.34, base + r * 0.36)], width=st)
        _flake(c, cx + r * 0.05, base + r * 0.22, r * 0.11, st * 0.7)
        c.line([(cx + r * 0.36, base), (cx + r * 0.24, base + r * 0.36)], width=st)
    elif kind == "thunder":
        x, y, k = cx, base - st, r
        c.polygon([(x + k * 0.08, y), (x - k * 0.18, y + k * 0.26), (x - k * 0.01, y + k * 0.26),
                   (x - k * 0.12, y + k * 0.5), (x + k * 0.2, y + k * 0.18), (x + k * 0.02, y + k * 0.18),
                   (x + k * 0.14, y)])


def _flake(c, x, y, r, st):
    for i in range(3):
        a = i * math.pi / 3
        c.line([(x - math.cos(a) * r, y - math.sin(a) * r), (x + math.cos(a) * r, y + math.sin(a) * r)],
               width=st)


# ---------------------------------------------------------------- helpers

def c_to_f(v):
    return None if v is None else v * 9 / 5 + 32


def val(d):
    return None if not d else d.get("value")


def compass(deg):
    if deg is None:
        return ""
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def hour_label(dt):
    h = dt.hour % 12 or 12
    return f"{h}{'a' if dt.hour < 12 else 'p'}"


def clock(dt):
    return dt.strftime("%-I:%M %p")


def battery_icon(c, x, y, pct, charging=False):
    w, h = 54, 26
    c.rect((x, y, x + w, y + h), outline=BLACK, width=2.5, radius=4)
    c.rect((x + w, y + 8, x + w + 5, y + h - 8), fill=BLACK)
    if pct is not None:
        fw = max(0, min(100, pct)) / 100 * (w - 8)
        c.rect((x + 4, y + 4, x + 4 + fw, y + h - 4), fill=BLACK if pct > 15 else DARK)
    if charging:
        cx, cy = x + w / 2, y + h / 2
        c.polygon([(cx + 3, cy - 11), (cx - 7, cy + 2), (cx - 1, cy + 2), (cx - 3, cy + 11),
                   (cx + 7, cy - 2), (cx + 1, cy - 2)], fill=WHITE)


# ---------------------------------------------------------------- main render

def render(data, location, now=None, battery=None, charging=False, next_update=None, sun=None, stale=False,
           local_temp=None, local_failed=False, version=None):
    tz = ZoneInfo(data.get("tz") or "America/New_York")
    now = now or datetime.now(tz)
    c = Canvas()
    M = 56  # page margin

    # ---- header
    c.text((M, 52), location, 40, "semibold", anchor="ls")
    c.text((W - M, 52), now.strftime("%A, %B %-d"), 32, "regular", fill=DARK, anchor="rs")
    c.line([(M, 76), (W - M, 76)], width=2)

    # ---- current conditions
    obs = data.get("obs") or {}
    hourly = data.get("hourly") or []
    h0 = hourly[0] if hourly else {}
    nws_temp = c_to_f(val(obs.get("temperature")))
    if nws_temp is None:
        nws_temp = h0.get("temperature")
    temp = local_temp if local_temp is not None else nws_temp
    cond = obs.get("textDescription") or h0.get("shortForecast") or ""
    kind, night = icon_kind(obs.get("icon") or h0.get("icon"))
    if obs.get("icon") is None and h0.get("isDaytime") is False:
        night = True

    draw_icon(c, M + 170, 245, 290, kind, night)
    tx = 470
    c.text((tx, 340), f"{round(temp)}°" if temp is not None else "--°", 250, "display", anchor="ls")
    c.text((tx + 8, 402), cond, 40, "medium", anchor="ls")

    daily = data.get("daily") or []
    hl = ""
    if daily:
        d0 = daily[0]
        if d0.get("isDaytime"):
            lo = daily[1]["temperature"] if len(daily) > 1 else None
            hl = f"High {d0['temperature']}°" + (f"   Low {lo}°" if lo is not None else "")
        else:
            hl = f"Tonight's low {d0['temperature']}°"
    c.text((tx + 8, 456), hl, 34, "regular", fill=DARK, anchor="ls")

    # detail strip
    feels = c_to_f(val(obs.get("windChill"))) or c_to_f(val(obs.get("heatIndex")))
    wind = val(obs.get("windSpeed"))
    hum = val(obs.get("relativeHumidity"))
    bits = []
    if local_failed:
        bits.append("Sensor offline")
    if feels is not None and temp is not None and abs(feels - temp) >= 2:
        bits.append(f"Feels like {round(feels)}°")
    if wind is not None:
        mph = round(wind * 0.621371)
        bits.append(f"Wind {compass(val(obs.get('windDirection')))} {mph} mph" if mph else "Calm")
    if hum is not None:
        bits.append(f"Humidity {round(hum)}%")
    y = 530
    c.rect((M, y - 44, W - M, y + 22), fill=None, outline=LIGHT, width=2, radius=12)
    size, sep = 30, "     ·     "
    while size > 20 and c.textlen(sep.join(bits), size) > W - 2 * M - 40:
        sep = "   ·   " if sep != "   ·   " else sep
        size -= 1 if sep == "   ·   " else 0
    c.text((W / 2, y), sep.join(bits), size, "regular", anchor="ms")

    # ---- next 12 hours
    top = 590
    c.text((M, top + 20), "NEXT 12 HOURS", 24, "semibold", fill=DARK, anchor="ls")
    hrs = hourly[:12]
    any_rain = any((val(h.get("probabilityOfPrecipitation")) or 0) >= 5 for h in hrs)
    c.text((W - M, top + 20), "chance of precipitation" if any_rain else "temperature · no precipitation expected",
           22, "regular", fill=MID, anchor="rs")
    if hrs:
        n = len(hrs)
        colw = (W - 2 * M) / n
        temp_y, bar_top, bar_bot, hour_y = top + 76, top + 118, top + 290, top + 330
        c.line([(M, bar_bot), (W - M, bar_bot)], width=2)
        for frac in ((0.5,) if any_rain else ()):
            yy = bar_bot - (bar_bot - bar_top) * frac
            for xx in range(M, W - M, 14):
                c.line([(xx, yy), (xx + 6, yy)], fill=LIGHT, width=1.5)
        for i, h in enumerate(hrs):
            cx = M + colw * (i + 0.5)
            dt = datetime.fromisoformat(h["startTime"]).astimezone(tz)
            c.text((cx, temp_y), f"{h['temperature']}°", 27, "medium", anchor="ms")
            p = val(h.get("probabilityOfPrecipitation")) or 0
            if any_rain and p > 0:
                bh = (bar_bot - bar_top) * p / 100
                c.rect((cx - colw * 0.32, bar_bot - bh, cx + colw * 0.32, bar_bot),
                       fill=BLACK if p >= 50 else MID)
                if p >= 5:
                    c.text((cx, bar_bot - bh - 10), f"{p}%", 22, "semibold", anchor="ms")
            c.text((cx, hour_y), hour_label(dt), 26, "regular", fill=DARK, anchor="ms")
        if not any_rain:
            temp_curve(c, hrs, M, colw, bar_top + 14, bar_bot - 14, bar_bot)

    # ---- multi-day forecast
    top = 975
    c.line([(M, top - 20), (W - M, top - 20)], width=2)
    days = group_days(daily, tz, now)[:5]
    if days:
        colw = (W - 2 * M) / len(days)
        for i, d in enumerate(days):
            cx = M + colw * (i + 0.5)
            if i:
                c.line([(M + colw * i, top + 10), (M + colw * i, top + 300)], fill=LIGHT, width=2)
            c.text((cx, top + 40), d["label"], 32, "semibold", anchor="ms")
            k, _ = icon_kind(d["icon"])
            draw_icon(c, cx, top + 120, 110, k, False)
            hi = f"{d['hi']}°" if d["hi"] is not None else "--"
            lo = f"{d['lo']}°" if d["lo"] is not None else "--"
            c.text((cx, top + 232), hi, 44, "semibold", anchor="ms")
            c.text((cx, top + 274), lo, 32, "regular", fill=DARK, anchor="ms")
            if d["pop"]:
                c.text((cx, top + 312), f"{d['pop']}% precip", 22, "regular", fill=DARK, anchor="ms")

    # ---- footer
    fy = H - 42
    c.line([(M, fy - 46), (W - M, fy - 46)], fill=LIGHT, width=2)
    if version:
        c.text((W / 2, fy - 72), f"v{version}", 24, "regular", fill=MID, anchor="ms")
    if sun:
        c.text((M, fy), f"Sunrise {clock(sun[0])}   Sunset {clock(sun[1])}", 26, "regular", fill=DARK, anchor="ls")
    upd = datetime.fromtimestamp(data.get("fetched_at", now.timestamp()), tz)
    right = f"{'Offline · data from ' if stale else 'Updated '}{clock(upd if stale else now)}"
    if next_update and (next_update - now).total_seconds() > 3600:
        right += f" · next {clock(next_update)}"
    bx = W - M - 60
    if battery is not None:
        pct = f"{round(battery)}%"
        battery_icon(c, bx, fy - 24, battery, charging)
        bx -= c.textlen(pct, 24, "medium") + 10
        c.text((bx, fy), pct, 24, "medium", anchor="ls")
    c.text((bx - 22, fy), right, 24, "regular", fill=DARK, anchor="rs")
    return c.finish()


def temp_curve(c, hrs, M, colw, y_top, y_bot, base):
    """Line graph of hourly temperature, shaded underneath; high/low points emphasised."""
    temps = [h["temperature"] for h in hrs]
    lo, hi = min(temps), max(temps)
    span = max(hi - lo, 6)  # don't exaggerate a 1-2 degree wobble
    mid = (hi + lo) / 2
    ys = [y_bot - (t - (mid - span / 2)) / span * (y_bot - y_top) for t in temps]
    xs = [M + colw * (i + 0.5) for i in range(len(temps))]
    pts = list(zip(xs, ys))
    c.polygon([(xs[0], base)] + pts + [(xs[-1], base)], fill=232)
    c.line(pts, fill=BLACK, width=4)
    marked = set()
    for (x, y), t in zip(pts, temps):
        if t in (hi, lo) and hi != lo and t not in marked:
            marked.add(t)
            c.circle(x, y, 9, fill=BLACK)
        else:
            c.circle(x, y, 6, fill=WHITE, outline=BLACK, width=3)


def group_days(daily, tz, now):
    """Collapse NWS 12-hour periods into calendar days (skipping today)."""
    out = {}
    order = []
    for p in daily:
        dt = datetime.fromisoformat(p["startTime"]).astimezone(tz)
        key = dt.date()
        if key not in out:
            out[key] = {"hi": None, "lo": None, "pop": 0, "icon": None, "date": key}
            order.append(key)
        d = out[key]
        pop = val(p.get("probabilityOfPrecipitation")) or 0
        d["pop"] = max(d["pop"], pop)
        if p.get("isDaytime"):
            d["hi"] = p["temperature"]
            d["icon"] = p.get("icon")
        else:
            # a night period belongs to the day that started that evening
            d["lo"] = p["temperature"]
            d["icon"] = d["icon"] or p.get("icon")
    days = [out[k] for k in order if k > now.date()]
    for d in days:
        d["label"] = d["date"].strftime("%a")
    return [d for d in days if d["hi"] is not None]
