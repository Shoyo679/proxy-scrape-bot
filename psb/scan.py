"""Read a channel's checkout webhooks between two points and turn them into attempts with their proxy.

Start / end can be a message link, a message ID, a date (2026-10-30), "today" or "yesterday". Both ends are
included: a start message is the first one read, an end date is read to its last minute.

Only the proxy's type and provider are kept (proxies.py); the proxy itself never leaves this module, and nothing is
written to disk.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

import discord

from . import proxies
from .parse import detect_bot, parse_checkout

MESSAGE_LINK = re.compile(r"discord(?:app)?\.com/channels/(\d+|@me)/(\d+)/(\d+)")
SNOWFLAKE = re.compile(r"^\d{15,22}$")
MAX_MESSAGES = 50_000   # one scrape reads at most this many messages
OK = ("success", "hold")
FAILS = ("declined", "error", "cancelled")


class BadPoint(ValueError):
    """A start / end the user typed that can't be read (the message says what to type instead)."""


@dataclass
class Point:
    """Where a scan starts or ends: a message (id) or a moment (when)."""
    id: int | None = None
    when: datetime | None = None
    channel_id: int | None = None   # from a message link: the channel it belongs to
    text: str = ""

    def after(self) -> discord.abc.Snowflake | datetime:
        """For channel.history(after=...): the start itself is included."""
        return discord.Object(id=self.id - 1) if self.id else self.when

    def before(self) -> discord.abc.Snowflake | datetime:
        """For channel.history(before=...): the end itself is included."""
        return discord.Object(id=self.id + 1) if self.id else self.when


def read_point(text: str, tz: tzinfo, end: bool = False, today: date | None = None) -> Point:
    """A message link / ID / date typed by the user -> Point. An end date means the end of that day."""
    raw = (text or "").strip()
    today = today or datetime.now(tz).date()
    if (link := MESSAGE_LINK.search(raw)):
        return Point(id=int(link.group(3)), channel_id=int(link.group(2)), text=raw)
    if SNOWFLAKE.match(raw):
        return Point(id=int(raw), text=raw)
    words = {"today": today, "yesterday": today - timedelta(days=1)}
    try:
        day = words.get(raw.lower()) or date.fromisoformat(raw)
    except ValueError:
        raise BadPoint(f"`{raw}` isn't a message link, a message ID or a date like 2026-10-30.") from None
    start = datetime.combine(day + timedelta(days=1) if end else day, time.min, tzinfo=tz)
    return Point(when=start, text=raw)


@dataclass
class Attempt:
    """One checkout webhook: when, which bot, the outcome and the proxy's label."""
    when: datetime
    bot: str
    status: str            # success, hold, declined, error, cancelled
    proxy: str             # proxies.label(): "Vaultedproxies", "ISP (no provider name)", "No proxy data"...
    ptype: str | None      # resi, mobile, isp, None

    @property
    def ok(self) -> bool:
        return self.status in OK


@dataclass
class Scan:
    attempts: list[Attempt] = field(default_factory=list)
    messages: int = 0      # every message read
    webhooks: int = 0      # webhook / bot messages read
    not_read: int = 0      # webhook / bot messages that aren't a Valor / Shikari / sniped.gg / Refract checkout
    capped: bool = False   # stopped at MAX_MESSAGES


def attempt_from(record: dict, tz: tzinfo, proxy: dict | None = None) -> Attempt | None:
    """A message (as a dict: source_name, embeds, created_at...) -> Attempt, or None if it isn't a checkout attempt.
    Valor's later order checks ("Order Still Good" / "Order Canceled!") aren't attempts and are left out."""
    checkout = parse_checkout(record)
    if checkout is None or checkout["order_check"]:
        return None
    if proxy is None:
        proxy = proxies.from_embed(record["embeds"][0])
    return Attempt(when=datetime.fromisoformat(record["created_at"]).astimezone(tz), bot=checkout["bot"],
                   status=checkout["status"], proxy=proxies.label(proxy["type"], proxy["provider"]), ptype=proxy["type"])


def _record(message: discord.Message) -> dict:
    return {"id": str(message.id), "day": "", "created_at": message.created_at.isoformat(),
            "channel_id": str(message.channel.id), "source_name": message.author.display_name,
            "content": message.content, "embeds": [e.to_dict() for e in message.embeds], "jump_url": message.jump_url}


async def scan(channel, start: Point, end: Point | None, tz: tzinfo, own_id: int, include_fails: bool = True,
               progress=None) -> Scan:
    """Read the channel from start to end (or now). progress(count) is awaited every 500 messages."""
    result = Scan()
    history = channel.history(limit=MAX_MESSAGES + 1, after=start.after(), before=end.before() if end else None,
                              oldest_first=True)
    async for message in history:
        result.messages += 1
        if result.messages > MAX_MESSAGES:
            result.messages -= 1
            result.capped = True
            break
        if progress and result.messages % 500 == 0:
            await progress(result.messages)
        if message.author.id == own_id or not (message.webhook_id or message.author.bot) or not message.embeds:
            continue
        result.webhooks += 1
        record = _record(message)
        try:
            attempt = attempt_from(record, tz)
        except Exception:   # one odd webhook never stops a scrape
            attempt = None
        if attempt is None:
            if detect_bot(record, record["embeds"][0]) is None:
                result.not_read += 1
            continue
        if attempt.ok or include_fails:
            result.attempts.append(attempt)
    return result
