"""Run: python -m unittest discover -s tests

Only made-up webhooks here: never real proxies, emails or order numbers.
"""
import asyncio
import sys
import unittest
import unittest.mock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discord  # noqa: E402

from psb import chart, proxies, report  # noqa: E402
from psb.bot import summary_embed  # noqa: E402
from psb.scan import BadPoint, attempt_from, read_point, scan  # noqa: E402

TZ = ZoneInfo("America/New_York")
SHIKARI_DESC = "[**Elite Trainer Box**](https://www.target.com/p/x/-/A-1010892076)"


def shikari(title="Successful Checkout", proxy="a.vaultedproxies.com:1:user:pass", when="2026-10-30T07:06:00+00:00"):
    fields = [{"name": "Site", "value": "Target"}, {"name": "Quantity", "value": "1"},
              {"name": "Order ID", "value": "||123||"}]
    if proxy:
        fields.append({"name": "Proxy", "value": f"||{proxy}||"})
    return {"id": "1", "day": "", "created_at": when, "channel_id": "1", "source_name": "Shikari", "content": "",
            "embeds": [{"title": title, "author": {"name": "Shikari"}, "description": SHIKARI_DESC, "fields": fields}],
            "jump_url": "https://discord.com/channels/1/1/1"}


class Settings(unittest.TestCase):
    def test_only_the_token_is_saved_and_times_are_local(self):
        import json
        import os
        import tempfile
        from psb import config
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.dict(os.environ, {"APPDATA": d}):
            config.save({"token": "abc", "timezone": "Asia/Kolkata"})
            self.assertEqual(json.loads(config.path().read_text(encoding="utf-8")), {"token": "abc"})
        tz = config.local_timezone()
        self.assertIsNotNone(datetime.now(tz).utcoffset())


class TokenCheck(unittest.TestCase):
    def test_looks_like_token(self):
        from psb.welcome import looks_like_token
        self.assertTrue(looks_like_token("M" * 26 + "." + "a" * 6 + "." + "b" * 38))
        for bad in ("", "hello", "abc.def", "a b.c d.e f" * 10, "https://discord.com/developers/applications"):
            self.assertFalse(looks_like_token(bad), bad)


class Points(unittest.TestCase):
    def test_links_ids_and_dates(self):
        p = read_point("https://discord.com/channels/111/222/1300000000000000000", TZ)
        self.assertEqual((p.id, p.channel_id), (1300000000000000000, 222))
        self.assertEqual(read_point(" 1300000000000000001 ", TZ).id, 1300000000000000001)
        start = read_point("2026-10-30", TZ)
        self.assertEqual(start.when, datetime(2026, 10, 30, tzinfo=TZ))
        self.assertEqual(read_point("2026-10-30", TZ, end=True).when, datetime(2026, 10, 31, tzinfo=TZ))   # whole day
        self.assertEqual(read_point("yesterday", TZ, today=date(2026, 10, 30)).when, datetime(2026, 10, 29, tzinfo=TZ))
        with self.assertRaises(BadPoint):
            read_point("last week", TZ)

    def test_message_points_include_themselves(self):
        p = read_point("1300000000000000000", TZ)
        self.assertEqual(p.after().id, 1299999999999999999)
        self.assertEqual(p.before().id, 1300000000000000001)


class Attempts(unittest.TestCase):
    def test_proxy_kept_as_provider_only(self):
        a = attempt_from(shikari(proxy="(My List) gw.proxy-haus.com:80:pkg-hausmob-secret:pw"), TZ)
        self.assertEqual((a.bot, a.status, a.proxy, a.ptype), ("shikari", "success", "Proxy-haus · mobile", "mobile"))
        self.assertNotIn("secret", repr(a))
        self.assertNotIn("My List", repr(a))
        self.assertEqual(attempt_from(shikari(proxy="1.2.3.4:80:u:p"), TZ).proxy, proxies.ISP)
        self.assertEqual(attempt_from(shikari(proxy=None), TZ).proxy, proxies.NO_PROXY)
        self.assertEqual(attempt_from(shikari(title="Order Cancelled"), TZ).status, "cancelled")
        self.assertEqual(a.when.tzinfo, TZ)

    def test_order_checks_are_not_attempts(self):
        check = shikari()
        check.update(source_name="Valor 3.0", embeds=[{"title": "Order Canceled! (Policy - Item Demand)",
                                                       "fields": [{"name": "Item", "value": "Tin"}]}])
        self.assertIsNone(attempt_from(check, TZ))


class Reports(unittest.TestCase):
    def build(self, minutes, status="success", proxy="a.vaultedproxies.com:1:u:p"):
        base = datetime(2026, 10, 30, 7, 6, tzinfo=timezone.utc)
        return [attempt_from(shikari(title="Successful Checkout" if status == "success" else "Order Cancelled",
                                     proxy=proxy, when=(base + timedelta(minutes=m)).isoformat()), TZ)
                for m in minutes]

    def test_columns_windows_and_totals(self):
        attempts = self.build([0, 0, 1, 3]) + self.build([1], "cancelled", "b.ipfist.com:1:u:p") \
            + self.build([200, 201])                       # a second burst over 3 hours later
        r = report.build(attempts)
        self.assertEqual((r.total, r.ok, r.windows, r.size), (7, 6, 2, 1))
        self.assertEqual(len(r.columns), 4 + 2)            # 3:06-3:09 and 6:26-6:27, the gap is cut out
        self.assertEqual(sum(c.total for c in r.columns), r.total)
        self.assertEqual(r.peak().total, 2)
        self.assertEqual([p.name for p in r.providers], ["Vaultedproxies", "Ipfist"])
        self.assertEqual(report.duration(r.active), "6m")
        self.assertEqual(sum(p.total for p in r.providers), r.total)

    def test_long_ranges_use_bigger_columns(self):
        r = report.build(self.build(range(0, 60 * 24 * 10, 37)))   # ten days of steady attempts
        self.assertLessEqual(len(r.columns), report.MAX_COLUMNS)
        self.assertGreater(r.size, 60)

    def test_image_and_embed(self):
        r = report.build(self.build([0, 0, 1]) + self.build([2], "cancelled", None) + self.build([3], proxy="1.2.3.4:80:u:p"))
        png = chart.render(r, "checkouts", "success + all fails")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        e = summary_embed(r, "checkouts", "success + all fails", SimpleNamespace(messages=9, not_read=1, capped=False),
                          "Oct 30, 2026")
        self.assertIn("**5** checkout webhooks", e.description)
        self.assertEqual(e.fields[0].value, "1) Vaultedproxies - 3 (100%)")
        self.assertIn("1 from other bots skipped", e.footer.text)
        self.assertEqual(chart.render(report.build([]), "x", "y")[:4], b"\x89PNG")   # empty never crashes


class Scanning(unittest.TestCase):
    def test_reads_only_checkout_webhooks(self):
        def message(i, author_bot, webhook, record=None):
            embeds = [discord.Embed.from_dict(record["embeds"][0])] if record else []
            return SimpleNamespace(id=i, author=SimpleNamespace(id=50 if i == 99 else 7, bot=author_bot,
                                                               display_name=record["source_name"] if record else "x"),
                                   webhook_id=1 if webhook else None, embeds=embeds, content="",
                                   created_at=datetime(2026, 10, 30, 7, i % 50, tzinfo=timezone.utc),
                                   channel=SimpleNamespace(id=1), jump_url="https://discord.com/channels/1/1/1")
        other = shikari()
        other.update(source_name="Some Other Bot", embeds=[{"title": "Hello", "fields": [{"name": "a", "value": "b"}]}])
        msgs = [message(1, False, True, shikari()), message(2, False, True, shikari(title="Order Cancelled")),
                message(3, False, False), message(4, True, False, other), message(99, True, False, shikari())]

        class Channel:
            def history(self, **kw):
                async def gen():
                    for m in msgs:
                        yield m
                return gen()

        s = asyncio.run(scan(Channel(), read_point("2026-10-30", TZ), None, TZ, own_id=50))
        self.assertEqual((s.messages, s.webhooks, s.not_read, len(s.attempts)), (5, 3, 1, 2))
        only_ok = asyncio.run(scan(Channel(), read_point("2026-10-30", TZ), None, TZ, own_id=50, include_fails=False))
        self.assertEqual([a.status for a in only_ok.attempts], ["success"])


if __name__ == "__main__":
    unittest.main()
