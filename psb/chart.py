"""The "Proxy Timeline" image posted with every scrape (PNG, 1600 px wide, drawn with Pillow).

  header      title, channel, day and time range, what was counted; big success rate on the right
  tiles       attempts, providers, peak column, active time, proxy coverage
  chart       attempts per column (green = success, red = failed); one row per proxy with a dot in every column it
              was used in (green = all success, red = all failed, amber = both) and its total + success rate
  busiest     the busiest columns with the proxies used in them
Drawn at twice the size and scaled down, so lines and text are smooth.
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .proxies import ISP, NO_PROXY
from .report import Report, duration, size_name

W = 1600
S = 2   # drawn at 2x
PAD = 36
BG, PANEL, PANEL_2, LINE = "#0e0f13", "#16171c", "#1d1e25", "#2a2b33"
INK, INK_2, MUTED = "#eceef3", "#b9bcc8", "#7d8090"
GREEN, RED, AMBER, ACCENT = "#3ddc84", "#f0505c", "#f5b13d", "#7c6cff"
MAX_ROWS = 7

_FONT_FILES = {
    "regular": ["segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"],
    "semibold": ["seguisb.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Helvetica.ttc"],
    "bold": ["segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Helvetica.ttc"],
}
_FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/TTF"),
              Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts")]
_fonts: dict = {}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """A system font (Segoe UI on Windows, DejaVu on Linux, Arial / Helvetica on Mac), Pillow's own as a last resort."""
    key = (size, weight)
    if key not in _fonts:
        found = None
        for name in _FONT_FILES[weight]:
            for d in _FONT_DIRS:
                if (d / name).exists():
                    found = ImageFont.truetype(str(d / name), size * S)
                    break
            if found:
                break
        _fonts[key] = found or ImageFont.load_default(size * S)
    return _fonts[key]


class Canvas:
    """ImageDraw in 1x units (everything is multiplied by S)."""

    def __init__(self, height: int):
        self.img = Image.new("RGB", (W * S, height * S), BG)
        self.d = ImageDraw.Draw(self.img)

    def box(self, x, y, w, h, fill, r=12, outline=None):
        self.d.rounded_rectangle((x * S, y * S, (x + w) * S, (y + h) * S), r * S, fill=fill,
                                 outline=outline, width=S if outline else 0)

    def rect(self, x, y, w, h, fill):
        if w > 0 and h > 0:
            self.d.rectangle((x * S, y * S, (x + w) * S, (y + h) * S), fill=fill)

    def line(self, x1, y1, x2, y2, fill=LINE, width=1):
        self.d.line((x1 * S, y1 * S, x2 * S, y2 * S), fill=fill, width=width * S)

    def dot(self, x, y, r, fill):
        self.d.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S), fill=fill)

    def text(self, x, y, s, size=16, fill=INK, weight="regular", anchor="la"):
        self.d.text((x * S, y * S), str(s), font=font(size, weight), fill=fill, anchor=anchor)

    def width(self, s, size=16, weight="regular") -> float:
        return self.d.textlength(str(s), font=font(size, weight)) / S

    def fit(self, s, max_w, size=16, weight="regular") -> str:
        s = str(s)
        if self.width(s, size, weight) <= max_w:
            return s
        while s and self.width(s + "…", size, weight) > max_w:
            s = s[:-1]
        return s + "…"

    def png(self) -> bytes:
        out = io.BytesIO()
        self.img.resize((self.img.width // S, self.img.height // S), Image.LANCZOS).save(out, "PNG", optimize=True)
        return out.getvalue()


def _rate_colour(rate: float) -> str:
    return GREEN if rate >= 0.75 else AMBER if rate >= 0.4 else RED


def _clock(t) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _span(r: Report) -> str:
    if r.first is None:
        return ""
    tz = r.first.strftime("%Z")
    if r.first.date() == r.last.date():
        return f"{r.first:%b %d, %Y} · {_clock(r.first)} – {_clock(r.last)} {tz}"
    return f"{r.first:%b %d} {_clock(r.first)} – {r.last:%b %d, %Y} {_clock(r.last)} {tz}"


def _column_label(c, size: int) -> str:
    if size >= 1440:
        return c.start.strftime("%b %d")
    if size >= 60:
        return c.start.strftime("%b %d %I %p").replace(" 0", " ")
    return _clock(c.start)


def render(r: Report, channel: str, counted: str) -> bytes:
    # named providers (top MAX_ROWS, the rest as "Others"), then ISP and "No proxy data" always on their own rows
    named = [p for p in r.providers if p.name not in (ISP, NO_PROXY)]
    plain = [p for p in r.providers if p.name in (ISP, NO_PROXY)]
    rows, others = named[:MAX_ROWS], named[MAX_ROWS:]
    n_rows = len(rows) + (1 if others else 0) + len(plain)
    busiest = r.busiest()
    plot_h, row_h = 210, 46
    chart_h = 60 + plot_h + 14 + n_rows * row_h + 40
    height = PAD + 108 + 24 + 104 + 24 + chart_h + (24 + 30 + 116 if busiest else 0) + 56
    c = Canvas(height)

    # --- header ---
    y = PAD
    c.dot(PAD + 30, y + 32, 30, PANEL_2)
    for rr, col in ((22, ACCENT), (14, PANEL_2), (8, ACCENT)):
        c.dot(PAD + 30, y + 32, rr, col)
    c.line(PAD + 30, y + 32, PAD + 52, y + 12, INK, 3)
    c.text(PAD + 76, y + 4, "Proxy Timeline", 34, INK, "bold")
    sub = " · ".join(s for s in (f"#{channel}", _span(r), counted) if s)
    c.text(PAD + 78, y + 52, c.fit(sub, W - 2 * PAD - 420), 18, MUTED)
    rate_col = _rate_colour(r.rate)
    c.text(W - PAD, y - 6, f"{round(r.rate * 100)}%", 72, rate_col, "bold", "ra")
    c.rect(W - PAD - 220, y + 86, 220, 6, PANEL_2)
    c.rect(W - PAD - 220, y + 86, 220 * r.rate, 6, rate_col)
    c.rect(W - PAD - 220 + 220 * r.rate, y + 86, 220 * (1 - r.rate), 6, RED if r.total else PANEL_2)
    c.text(W - PAD, y + 98, "SUCCESS RATE", 12, MUTED, "semibold", "ra")
    y += 108 + 24

    # --- tiles ---
    peak = r.peak()
    tiles = [
        ("ATTEMPTS", r.total, f"{r.ok} success · {r.total - r.ok} failed"),
        ("PROVIDERS", r.provider_count, "named resi / mobile providers"),
        (f"PEAK {size_name(r.size).upper()}", f"{peak.total if peak else 0}",
         f"{_column_label(peak, r.size)} · {peak.ok} success" if peak and peak.total else "–"),
        ("ACTIVE", duration(r.active) if r.total else "–",
         f"{r.windows} burst{'s' if r.windows != 1 else ''}" + (" · quiet gaps cut from chart"
                                                              if r.columns and r.columns[-1].window else "")),
        ("PROXY COVERAGE", f"{round(100 * r.with_proxy / r.total) if r.total else 0}%",
         f"{r.with_proxy} of {r.total} with proxy data"),
    ]
    tw = (W - 2 * PAD - 4 * 14) / 5
    for i, (label, value, note) in enumerate(tiles):
        x = PAD + i * (tw + 14)
        c.box(x, y, tw, 104, PANEL, 12, LINE)
        c.text(x + 18, y + 16, label, 12, MUTED, "semibold")
        c.text(x + 18, y + 34, value, 32, INK, "bold")
        c.text(x + 18, y + 78, c.fit(note, tw - 30), 13, INK_2)
    y += 104 + 24

    # --- chart ---
    c.box(PAD, y, W - 2 * PAD, chart_h, PANEL, 14, LINE)
    c.text(PAD + 20, y + 20, f"ATTEMPTS PER {size_name(r.size).upper()}", 13, MUTED, "semibold")
    lx = W - PAD - 20
    for name, col in ((f"Failed {r.total - r.ok}", RED), (f"Success {r.ok}", GREEN)):
        c.text(lx, y + 20, name, 13, INK_2, "semibold", "ra")
        lx -= c.width(name, 13, "semibold") + 8
        c.dot(lx - 5, y + 28, 5, col)
        lx -= 26
    left, right = PAD + 250, W - PAD - 230
    cols = r.columns
    n = max(len(cols), 1)
    cw = (right - left) / n
    top = y + 60
    base = top + plot_h
    vmax = max([col.total for col in cols] + [1])
    for frac in (0, 0.5, 1):
        gy = base - plot_h * frac
        c.line(left, gy, right, gy, LINE)
        c.text(left - 10, gy, round(vmax * frac), 12, MUTED, anchor="rm")
    bw = max(min(cw * 0.62, 44), 2)
    for i, col in enumerate(cols):
        cx = left + cw * (i + 0.5)
        if i and col.window != cols[i - 1].window:   # quiet gap left out
            gx = left + cw * i
            for k in range(0, int(plot_h + n_rows * row_h), 8):
                c.line(gx, top + k, gx, top + k + 4, MUTED)
        if not col.total:
            continue
        h_ok = plot_h * col.ok / vmax
        h_fail = plot_h * col.failed / vmax
        c.rect(cx - bw / 2, base - h_ok, bw, h_ok, GREEN)
        c.rect(cx - bw / 2, base - h_ok - h_fail, bw, h_fail, RED)
        if cw >= 16 or col is peak:
            c.text(cx, base - h_ok - h_fail - 6, col.total, 12, INK_2, "semibold", "md")

    # proxy rows
    ry = base + 14
    shown = [(p.name, p.ptype, p.total, p.ok) for p in rows]
    if others:
        shown.append((f"Others ({len(others)})", "others", sum(p.total for p in others), sum(p.ok for p in others)))
    shown += [(p.name, p.ptype, p.total, p.ok) for p in plain]
    other_names = {p.name for p in others}
    for k, (name, ptype, total, ok) in enumerate(shown):
        if k % 2 == 0:
            c.rect(PAD + 1, ry, W - 2 * PAD - 2, row_h, PANEL_2)
        mid = ry + row_h / 2
        grey = name in (ISP, NO_PROXY)
        label = c.fit(name, 200 if k else 150, 16, "semibold")
        c.text(PAD + 20, mid - 10, label, 16, MUTED if grey else INK, "semibold", "lm")
        if k == 0 and not grey:
            tx = PAD + 28 + c.width(label, 16, "semibold")
            c.box(tx, mid - 19, 40, 18, "#173d2a", 5)
            c.text(tx + 20, mid - 10, "TOP", 11, GREEN, "bold", "mm")
        note = {"resi": "residential", "mobile": "mobile", "isp": "IP only, no provider name",
                None: "no proxy field in the webhook", "others": "smaller providers"}.get(ptype, "")
        c.text(PAD + 20, mid + 11, note, 12, MUTED, anchor="lm")
        for i, col in enumerate(cols):
            if ptype == "others":
                used = sum(col.proxies[p] for p in other_names)
                good = sum(col.proxies_ok[p] for p in other_names)
            else:
                used, good = col.proxies[name], col.proxies_ok[name]
            if used:
                colour = GREEN if good == used else RED if good == 0 else AMBER
                c.dot(left + cw * (i + 0.5), mid, min(4 + used * 1.2, min(cw * 0.42, 10)) if cw > 8 else 3, colour)
        rate = ok / total if total else 0
        c.text(W - PAD - 20, mid - 10, f"{round(rate * 100)}% success", 13, _rate_colour(rate), "semibold", "rm")
        c.text(right + 14, mid - 10, f"{total}", 18, INK, "bold", "lm")
        c.text(right + 18 + c.width(total, 18, "bold"), mid - 9, "attempt" if total == 1 else "attempts", 12, MUTED, anchor="lm")
        c.rect(right + 14, mid + 10, W - PAD - 34 - right, 4, LINE)
        c.rect(right + 14, mid + 10, (W - PAD - 34 - right) * rate, 4, _rate_colour(rate))
        ry += row_h

    # time labels under the rows
    ly = ry + 12
    if cols:
        step = max(1, round(90 / cw))
        last_x = -1e9
        for i, col in enumerate(cols):
            new_window = i == 0 or col.window != cols[i - 1].window
            x = left + cw * (i + 0.5)
            if (new_window or i % step == 0) and x - last_x >= 80:
                c.text(x, ly, _column_label(col, r.size), 12, MUTED, anchor="ma")
                last_x = x
    y += chart_h + 24

    # --- busiest ---
    if busiest:
        c.text(PAD, y, f"BUSIEST {size_name(r.size).upper()}S" if r.size == 1 else "BUSIEST MOMENTS", 13, MUTED, "semibold")
        y += 30
        bw2 = (W - 2 * PAD - 3 * 14) / 4
        for i, col in enumerate(busiest):
            x = PAD + i * (bw2 + 14)
            c.box(x, y, bw2, 116, PANEL, 12, LINE)
            c.text(x + 16, y + 14, _column_label(col, r.size), 20, INK, "bold")
            c.text(x + bw2 - 16, y + 12, col.total, 24, _rate_colour(col.ok / col.total), "bold", "ra")
            c.text(x + 16, y + 44, f"{col.ok} success" + (f" · {col.failed} failed" if col.failed else ""), 13, INK_2)
            c.rect(x + 16, y + 68, bw2 - 32, 5, PANEL_2)
            c.rect(x + 16, y + 68, (bw2 - 32) * col.ok / col.total, 5, GREEN)
            c.rect(x + 16 + (bw2 - 32) * col.ok / col.total, y + 68, (bw2 - 32) * col.failed / col.total, 5, RED)
            short = {ISP: "ISP", NO_PROXY: "No proxy"}
            used = ", ".join(f"{short.get(p, p)} ×{k}" for p, k in col.proxies.most_common())
            c.text(x + 16, y + 84, c.fit(used, bw2 - 32, 13), 13, INK_2)
        y += 116
    c.text(W / 2, height - 30, "Times shown in the server owner's timezone setting · only proxy provider and type are "
                               "shown, never proxy logins", 12, MUTED, anchor="mm")
    return c.png()

