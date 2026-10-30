"""Numbers for one scrape: totals, providers, time columns, busiest moments. Pure (no Discord, no drawing).

Definitions:
  success = "Checked Out" / "Successful Checkout" / review hold
  failed  = declined, error or cancelled
  success rate = success / all attempts read
  proxy coverage = attempts whose webhook had a proxy / all attempts
Time columns: attempts are split into windows wherever nothing came in for GAP_MINUTES (the quiet time is left out of
the chart), then each window is cut into columns of one size (1 min, 2 min, 5 min ... 1 day) so the chart has at most
MAX_COLUMNS. A long scrape with many windows uses plain columns across the whole time instead.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .proxies import ISP, NO_PROXY
from .scan import Attempt

GAP_MINUTES = 15
MAX_COLUMNS = 60
SIZES = [1, 2, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440]   # column sizes, minutes
MAX_WINDOWS = 12   # more quiet gaps than this: plain columns across the whole time


@dataclass
class Provider:
    name: str
    ptype: str | None
    total: int = 0
    ok: int = 0

    @property
    def rate(self) -> float:
        return self.ok / self.total if self.total else 0.0


@dataclass
class Column:
    start: datetime
    window: int                                    # which quiet-gap window it belongs to
    ok: int = 0
    failed: int = 0
    proxies: Counter = field(default_factory=Counter)        # proxy label -> attempts
    proxies_ok: Counter = field(default_factory=Counter)     # proxy label -> successes

    @property
    def total(self) -> int:
        return self.ok + self.failed


@dataclass
class Report:
    attempts: list[Attempt]
    total: int
    ok: int
    fails: Counter                     # declined / error / cancelled -> count
    providers: list[Provider]          # most attempts first; ISP and "No proxy data" included
    columns: list[Column]
    size: int                          # column size, minutes
    windows: int                       # bursts of activity (separated by GAP_MINUTES of quiet)
    first: datetime | None
    last: datetime | None
    active: timedelta                  # time inside the windows (quiet gaps left out)

    @property
    def rate(self) -> float:
        return self.ok / self.total if self.total else 0.0

    @property
    def with_proxy(self) -> int:
        return sum(p.total for p in self.providers if p.ptype is not None)

    @property
    def provider_count(self) -> int:
        """Named providers (resi / mobile); ISP proxies have no provider name."""
        return sum(1 for p in self.providers if p.ptype in ("resi", "mobile"))

    def peak(self) -> Column | None:
        return max(self.columns, key=lambda c: (c.total, -c.start.timestamp()), default=None)

    def busiest(self, n: int = 4) -> list[Column]:
        top = sorted((c for c in self.columns if c.total), key=lambda c: (-c.total, c.start))[:n]
        return sorted(top, key=lambda c: c.start)


def _windows(times: list[datetime]) -> list[list[datetime]]:
    out: list[list[datetime]] = []
    for t in times:
        if out and t - out[-1][-1] <= timedelta(minutes=GAP_MINUTES):
            out[-1].append(t)
        else:
            out.append([t])
    return out


def _floor(t: datetime, minutes: int) -> datetime:
    """Start of t's column: whole minutes for small sizes, whole hours / days (local time) for big ones."""
    t = t.replace(second=0, microsecond=0)
    if minutes >= 1440:
        return t.replace(hour=0, minute=0)
    if minutes >= 60:
        return t.replace(hour=t.hour - t.hour % (minutes // 60), minute=0)
    return t.replace(minute=t.minute - t.minute % minutes)


def _columns_for(spans: list[tuple[datetime, datetime]], size: int) -> list[tuple[datetime, int]]:
    cols = []
    for w, (a, b) in enumerate(spans):
        t = _floor(a, size)
        while t <= b:
            cols.append((t, w))
            t += timedelta(minutes=size)
    return cols


def build(attempts: list[Attempt]) -> Report:
    attempts = sorted(attempts, key=lambda a: a.when)
    times = [a.when for a in attempts]
    groups = _windows(times)
    if len(groups) > MAX_WINDOWS:
        spans = [(times[0], times[-1])] if times else []
    else:
        spans = [(g[0], g[-1]) for g in groups]
    size, cols = SIZES[-1], []
    for s in SIZES:
        cols = _columns_for(spans, s)
        if len(cols) <= MAX_COLUMNS:
            size = s
            break
    columns = [Column(start=t, window=w) for t, w in cols]
    index = {(c.start, c.window): c for c in columns}
    for a in attempts:
        w = next(i for i, (lo, hi) in enumerate(spans) if lo <= a.when <= hi)
        col = index[(_floor(a.when, size), w)]
        col.proxies[a.proxy] += 1
        if a.ok:
            col.ok += 1
            col.proxies_ok[a.proxy] += 1
        else:
            col.failed += 1

    providers: dict[str, Provider] = {}
    for a in attempts:
        p = providers.setdefault(a.proxy, Provider(a.proxy, a.ptype))
        p.total += 1
        p.ok += a.ok
    order = sorted(providers.values(), key=lambda p: (p.name in (ISP, NO_PROXY), -p.total, -p.ok, p.name))
    # active time and window count always come from the real windows, even when the chart uses plain columns
    active = sum((g[-1] - g[0] + timedelta(minutes=1) for g in groups), timedelta())
    return Report(attempts=attempts, total=len(attempts), ok=sum(a.ok for a in attempts),
                  fails=Counter(a.status for a in attempts if not a.ok), providers=order, columns=columns, size=size,
                  windows=len(groups), first=times[0] if times else None, last=times[-1] if times else None,
                  active=active)


def duration(d: timedelta) -> str:
    """4m, 1h 20m, 2d 3h."""
    minutes = int(d.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def size_name(minutes: int) -> str:
    return {1: "minute", 60: "hour", 1440: "day"}.get(minutes) or (f"{minutes // 60} hours" if minutes >= 60 else f"{minutes} min")
