"""The "Proxy Timeline" image posted with every scrape (PNG, 2000 px wide, drawn with Pillow).

  header    logo, title, channel · day · time range · what was counted; big success rate + split bar on the right
  stats     one strip: checkouts, providers, peak minute, active time, proxy coverage
  timeline  checkouts per column (green = ok, red = failed) in fixed-width columns, the peak column highlighted;
            one row per proxy provider with a pie dot in every column it was used in (size = how many, slices = ok /
            failed) and its total, success rate and split bar on the right
  busiest   up to 6 busiest columns with the providers used in them
Drawn at twice the size and scaled down, so lines and text are smooth.
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .proxies import ISP, NO_PROXY
from .report import Report, duration, size_name

W = 2000
S = 2   # drawn at 2x
PAD = 57
BG, PANEL, PANEL_2, LINE = "#18181b", "#232327", "#2c2c31", "#36363c"
INK, INK_2, MUTED = "#f2f2f4", "#c4c4cc", "#8a8a94"
GREEN, RED, AMBER, ACCENT = "#36d77d", "#ef4a4f", "#f5a524", "#7c5cff"
TOP_ROW = "#1f2a24"
MAX_ROWS = 5          # named providers with their own row; the rest go in "Others"
COL_W = 57            # widest a column gets
ROW_H = 74

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

    def box(self, x, y, w, h, fill, r=16, outline=None):
        self.d.rounded_rectangle((x * S, y * S, (x + w) * S, (y + h) * S), r * S, fill=fill,
                                 outline=outline, width=2 * S if outline else 0)

    def rect(self, x, y, w, h, fill):
        if w > 0 and h > 0:
            self.d.rectangle((x * S, y * S, (x + w) * S, (y + h) * S), fill=fill)

    def line(self, x1, y1, x2, y2, fill=LINE, width=1):
        self.d.line((x1 * S, y1 * S, x2 * S, y2 * S), fill=fill, width=width * S)

    def dot(self, x, y, r, fill):
        self.d.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S), fill=fill)

    def pie(self, x, y, r, ok, failed):
        """A dot split into ok (green) and failed (red) slices."""
        if not failed or not ok:
            return self.dot(x, y, r, GREEN if ok else RED)
        box = ((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S)
        split = -90 + 360 * ok / (ok + failed)
        self.d.pieslice(box, -90, split, fill=GREEN)
        self.d.pieslice(box, split, 270, fill=RED)

    def split_bar(self, x, y, w, h, ok, failed):
        """A rounded bar: green for the ok share, red for the rest."""
        total = ok + failed
        self.box(x, y, w, h, PANEL_2, h / 2)
        if not total:
            return
        self.box(x, y, w, h, RED if failed else GREEN, h / 2)
        if ok and failed:
            self.box(x, y, w * ok / total, h, GREEN, h / 2)
            self.rect(x + w * ok / total - h / 2, y, h / 2, h, GREEN)   # square edge where green meets red

    def text(self, x, y, s, size=16, fill=INK, weight="regular", anchor="la", tracking=0):
        s = str(s)
        if not tracking:
            self.d.text((x * S, y * S), s, font=font(size, weight), fill=fill, anchor=anchor)
            return
        total = self.width(s, size, weight, tracking)   # letter-spaced labels: drawn letter by letter
        x0 = x - total if anchor[0] == "r" else x - total / 2 if anchor[0] == "m" else x
        for ch in s:
            self.d.text((x0 * S, y * S), ch, font=font(size, weight), fill=fill, anchor="l" + anchor[1])
            x0 += self.width(ch, size, weight) + tracking

    def width(self, s, size=16, weight="regular", tracking=0) -> float:
        s = str(s)
        return self.d.textlength(s, font=font(size, weight)) / S + tracking * max(len(s) - 1, 0)

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


def _tz(r: Report) -> str:
    return r.first.strftime("%Z") if r.first else ""


def _label(t, size: int) -> str:
    if size >= 1440:
        return t.strftime("%b %d")
    if size >= 60:
        return t.strftime("%b %d, %I %p").replace(" 0", " ")
    return _clock(t)


def _logo(c: Canvas, x, y, r):
    """Our own mark: a target with a pointer (same as the app icon)."""
    c.dot(x, y, r, ACCENT)
    c.dot(x, y, r * 0.68, PANEL)
    c.dot(x, y, r * 0.42, ACCENT)
    c.dot(x, y, r * 0.18, PANEL)
    c.line(x, y, x + r * 0.62, y - r * 0.62, INK, 4)
    c.dot(x, y, r * 0.1, GREEN)


def _marks(r: Report, cw: float) -> set[int]:
    """Columns that get a time label: each window's first column and round times about every 150 px."""
    out = {i for i, col in enumerate(r.columns) if i == 0 or col.window != r.columns[i - 1].window}
    if r.size >= 60 or not r.columns:
        every = max(1, round(150 / cw))
        return out | set(range(0, len(r.columns), every))
    for step in (5, 10, 15, 30, 60, 120, 240):   # minutes between labels
        if step >= r.size and step / r.size * cw >= 150:
            break
    for i, col in enumerate(r.columns):
        if (col.start.hour * 60 + col.start.minute) % step == 0:
            out.add(i)
    return out


def render(r: Report, channel: str, counted: str) -> bytes:
    named = [p for p in r.providers if p.name not in (ISP, NO_PROXY)]
    plain = [p for p in r.providers if p.name in (ISP, NO_PROXY)]
    rows, others = named[:MAX_ROWS], named[MAX_ROWS:]
    shown = [(p.name, p.ptype, p.total, p.ok, {p.name}) for p in rows]
    if others:
        shown.append((f"Others ({len(others)})", "others", sum(p.total for p in others), sum(p.ok for p in others),
                      {p.name for p in others}))
    shown += [(p.name, p.ptype, p.total, p.ok, {p.name}) for p in plain]
    busiest = r.busiest(6)
    unit = size_name(r.size)
    plot_h = 200
    chart_h = 100 + plot_h + 16 + len(shown) * ROW_H + 100
    height = 211 + 137 + 29 + chart_h + (40 + 50 + 175 if busiest else 0) + 110
    c = Canvas(height)
    tz = _tz(r)

    # --- header ---
    _logo(c, PAD + 40, 102, 40)
    c.text(PAD + 106, 84, "Proxy Timeline", 46, INK, "bold", "ls")
    if r.first and r.first.date() == r.last.date():
        when = [f"{r.first:%b %d, %Y}", f"{_clock(r.first)} – {_clock(r.last)} {tz}"]
    elif r.first:
        when = [f"{r.first:%b %d} {_clock(r.first)} – {r.last:%b %d, %Y} {_clock(r.last)} {tz}"]
    else:
        when = []
    x = PAD + 106
    for k, part in enumerate([f"#{channel}"] + when + [counted]):
        if k:
            c.text(x + 14, 137, "·", 21, MUTED, "semibold", "lm")
            x += 36
        part = c.fit(part, W - 420 - x, 21, "semibold")
        c.text(x, 137, part, 21, INK_2, "semibold", "lm")
        x += c.width(part, 21, "semibold")
    rate_col = _rate_colour(r.rate)
    c.text(W - PAD, 136, f"{round(r.rate * 100)}%", 92, rate_col, "bold", "rs")
    c.text(W - PAD, 152, "SUCCESS RATE", 17, INK_2, "semibold", "rm", tracking=2.2)
    c.split_bar(W - PAD - 240, 172, 240, 9, r.ok, r.total - r.ok)

    # --- stats strip ---
    y = 211
    c.box(PAD, y, W - 2 * PAD, 137, PANEL, 18)
    peak = r.peak()
    tiles = [
        ("CHECKOUTS", f"{r.total}", "", f"{r.ok} ok · {r.total - r.ok} failed"),
        ("PROVIDERS", f"{r.provider_count}", "", "named resi / mobile providers"),
        (f"PEAK {unit.upper()}", f"{peak.total if peak else 0}", "checkouts",
         f"{_label(peak.start, r.size)} {tz}" if peak and peak.total else "–"),
        ("ACTIVE", duration(r.active) if r.total else "–", "",
         f"{r.windows} drop window{'s' if r.windows != 1 else ''}"),
        ("PROXY COVERAGE", f"{round(100 * r.with_proxy / r.total) if r.total else 0}%", "",
         f"{r.with_proxy} of {r.total} with proxy data"),
    ]
    tw = (W - 2 * PAD) / 5
    for i, (label, value, unit_word, note) in enumerate(tiles):
        x = PAD + i * tw + 34
        if i:
            c.line(PAD + i * tw, y + 26, PAD + i * tw, y + 111, LINE)
        c.text(x, y + 35, label, 16, MUTED, "semibold", "lm", tracking=2)
        c.text(x, y + 88, value, 38, INK, "bold", "ls")
        if unit_word:
            c.text(x + c.width(value, 38, "bold") + 8, y + 88, unit_word, 21, INK_2, "regular", "ls")
        c.text(x, y + 109, c.fit(note, tw - 50, 19), 19, INK_2, anchor="lm")

    # --- timeline ---
    y = 211 + 137 + 29
    c.box(PAD, y, W - 2 * PAD, chart_h, PANEL, 18)
    c.text(PAD + 34, y + 54, f"CHECKOUTS PER {unit.upper()}", 19, INK_2, "semibold", "lm", tracking=2.2)
    c.text(PAD + 34 + c.width(f"CHECKOUTS PER {unit.upper()}", 19, "semibold", 2.2) + 20, y + 55,
           f"times in {tz}", 16, MUTED, anchor="lm")
    lx = W - PAD - 34
    for name, col in ((f"Failed {r.total - r.ok}", RED), (f"Success {r.ok}", GREEN)):
        c.text(lx, y + 54, name, 17, INK, "semibold", "rm")
        lx -= c.width(name, 17, "semibold") + 14
        c.dot(lx, y + 54, 7, col)
        lx -= 34
    cols = r.columns
    left, right = PAD + 333, W - PAD - 340
    cw = min(COL_W, (right - left) / max(len(cols), 1))
    top = y + 134
    base = top + plot_h - 20
    rows_top = base + 16
    rows_end = rows_top + len(shown) * ROW_H
    vmax = max([col.total for col in cols] + [1])
    c.line(left - 18, top, left + cw * len(cols) + 180, top, LINE)
    c.line(left - 18, base, left + cw * len(cols), base, LINE)
    c.text(left - 28, top, vmax, 17, MUTED, anchor="rm")
    c.text(left - 28, base, 0, 17, MUTED, anchor="rm")
    peak_i = cols.index(peak) if peak and peak.total else None
    if peak_i is not None:   # highlight band through the chart and the rows
        c.rect(left + cw * peak_i, top - 30, cw, rows_end - top + 30, PANEL_2)
    marks = _marks(r, cw)
    for i in sorted(marks):
        if i != peak_i and i:
            c.line(left + cw * i + cw / 2, top - 30, left + cw * i + cw / 2, rows_end, LINE)
    for i, col in enumerate(cols):
        if i and col.window != cols[i - 1].window:   # idle gap removed
            gx = left + cw * i
            for k in range(int(top - 30), int(rows_end), 10):
                c.line(gx, k, gx, k + 5, MUTED)
    bw = max(min(cw * 0.42, 22), 3)
    for i, col in enumerate(cols):
        if not col.total:
            continue
        cx = left + cw * (i + 0.5)
        h_ok = (base - top) * col.ok / vmax
        h_fail = (base - top) * col.failed / vmax
        if col.failed:
            c.box(cx - bw / 2, base - h_ok - h_fail, bw, h_fail + (4 if col.ok else 0), RED, 3)
        if col.ok:
            c.box(cx - bw / 2, base - h_ok, bw, h_ok, GREEN, 3)
        if col.failed and col.ok:
            c.rect(cx - bw / 2, base - h_ok - 2, bw, 3, PANEL if i != peak_i else PANEL_2)   # thin gap
        if col.total >= 2 and (cw >= 30 or i == peak_i):
            c.text(cx, base - h_ok - h_fail - 8, col.total, 18, INK, "semibold", "ms")

    # provider rows
    for k, (name, ptype, total, ok, names) in enumerate(shown):
        ry = rows_top + k * ROW_H
        mid = ry + ROW_H / 2
        grey = ptype in (None, "isp")
        if k == 0 and not grey:
            c.rect(PAD + 17, ry, W - 2 * PAD - 34, ROW_H, TOP_ROW)
        c.line(PAD + 34, ry + ROW_H, W - PAD - 34, ry + ROW_H, "#2a2a2f")
        label = c.fit(name, 230 if k == 0 and not grey else 290, 25, "semibold")
        c.text(PAD + 34, mid - 2, label, 25, MUTED if grey else INK, "semibold", "ls")
        if k == 0 and not grey:
            tx = PAD + 34 + c.width(label, 25, "semibold") + 12
            c.box(tx, mid - 23, 50, 25, "#1f4a33", 6)
            c.text(tx + 25, mid - 10.5, "TOP", 15, GREEN, "bold", "mm")
        note = {"resi": "residential", "mobile": "mobile", "isp": "IP only, no provider name",
                None: "no proxy field in the webhook", "others": f"{len(names)} smaller providers"}.get(ptype, "")
        c.text(PAD + 34, mid + 18, note, 17, MUTED, anchor="lm")
        biggest = max([sum(col.proxies[p] for p in names) for col in cols] + [1])
        for i, col in enumerate(cols):
            used = sum(col.proxies[p] for p in names)
            if used:
                good = sum(col.proxies_ok[p] for p in names)
                radius = min(5 + 8 * (used - 1) / max(biggest - 1, 1), cw * 0.4) if cw > 12 else 3
                c.pie(left + cw * (i + 0.5), mid, radius, good, used - good)
        rate = ok / total if total else 0
        sx = W - PAD - 282
        c.text(sx, mid - 8, total, 26, INK, "bold", "ls")
        c.text(sx + c.width(total, 26, "bold") + 8, mid - 8, "checkout" if total == 1 else "checkouts", 19, INK_2,
               anchor="ls")
        c.text(W - PAD - 34, mid - 8, f"{round(rate * 100)}% success", 19, _rate_colour(rate), "semibold", "rs")
        c.split_bar(sx, mid + 6, W - PAD - 34 - sx, 8, ok, total - ok)

    # time labels
    ly = rows_end + 14
    used_x: list[float] = []
    if peak_i is not None:
        px = left + cw * (peak_i + 0.5)
        c.d.polygon([((px - 7) * S, (ly + 10) * S), ((px + 7) * S, (ly + 10) * S), (px * S, (ly) * S)], fill=INK_2)
        c.text(px, ly + 30, _label(peak.start, r.size), 19, INK, "semibold", "mm")
        used_x.append(px)
    for i in sorted(marks):
        x = left + cw * (i + 0.5)
        if all(abs(x - u) >= 120 for u in used_x):
            c.text(x, ly + 30, _label(cols[i].start, r.size), 18, MUTED, anchor="mm")
            used_x.append(x)

    # --- busiest ---
    y = 211 + 137 + 29 + chart_h + 40
    if busiest:
        c.text(PAD, y + 12, f"BUSIEST {unit.upper()}S" if r.size in (1, 60, 1440) else "BUSIEST MOMENTS", 21, INK_2,
               "semibold", "lm", tracking=2.4)
        y += 50
        gap = 24
        bw2 = (W - 2 * PAD - 5 * gap) / 6
        short = {ISP: "ISP", NO_PROXY: "No proxy"}
        for i, col in enumerate(busiest):
            x = PAD + i * (bw2 + gap)
            c.box(x, y, bw2, 175, PANEL, 16, LINE if col is peak else None)
            c.text(x + 23, y + 36, _label(col.start, r.size), 27, INK, "bold", "lm")
            c.text(x + bw2 - 23, y + 36, col.total, 32, _rate_colour(col.ok / col.total), "bold", "rm")
            c.text(x + 23, y + 74, f"{col.ok} ok" + (f" · {col.failed} failed" if col.failed else ""), 18, INK_2,
                   anchor="lm")
            c.split_bar(x + 23, y + 96, bw2 - 46, 7, col.ok, col.failed)
            used = ", ".join(f"{short.get(p, p)} ×{n}" for p, n in col.proxies.most_common())
            c.text(x + 23, y + 136, c.fit(used, bw2 - 46, 20, "semibold"), 20, INK_2, "semibold", "lm")
        y += 175

    # --- footer ---
    fy = height - 70
    c.line(PAD, fy, W - PAD, fy, LINE)
    gaps = " · idle gaps over 15m removed" if cols and cols[-1].window else ""
    c.text(PAD, fy + 32, f"Times are webhook post times ({tz}, this computer's timezone) · provider names only, never "
                         f"proxy logins{gaps}", 18, MUTED, anchor="lm")
    return c.png()
