"""The Discord bot: /proxy scrape and /proxy help.

/proxy scrape start:<message link / ID / date> [end:...] [include:...] [channel:...]
  Reads that channel's checkout webhooks from start to end (or now) and posts a summary + the Proxy Timeline image
  in the channel. Needs Manage Server by default (server owners can change who may use it in Server Settings >
  Integrations). One scrape at a time per server.
"""
import asyncio
import io
import logging
import subprocess
import sys
import webbrowser
from datetime import datetime

import discord
from discord import app_commands

from . import chart, report
from .proxies import ISP, NO_PROXY
from .scan import BadPoint, read_point, scan
from .version import __version__

PERMISSIONS = 117760   # View Channel, Send Messages, Embed Links, Attach Files, Read Message History
TYPE_NAMES = {"resi": "Residential", "mobile": "Mobile", "isp": "ISP (IP only)", None: "No proxy data"}


def invite_link(app_id: int) -> str:
    return (f"https://discord.com/oauth2/authorize?client_id={app_id}&scope=bot+applications.commands"
            f"&permissions={PERMISSIONS}")


def open_invite(link: str) -> None:
    """Open the "add to server" page in the browser and copy the link (links in a console window are hard to use)."""
    try:
        if sys.platform == "win32":
            subprocess.run("clip", input=link.encode("utf-16-le"), check=False)
        webbrowser.open(link)
        print("Opened the 'add to server' page in your browser (the link is also copied: Ctrl+V to paste it).")
    except Exception:
        pass


class ProxyBot(discord.Client):
    def __init__(self, tz, invite: bool = False):
        self.invite = invite   # open the "add to server" page even if the bot is already in a server
        intents = discord.Intents.default()
        intents.message_content = True   # needed to read webhook embeds (switch it on in the Developer Portal)
        super().__init__(intents=intents)
        self.tz = tz
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(ProxyCommands(self))
        self.busy: set[int] = set()

    async def sync_guild(self, guild: discord.Guild) -> None:
        """Commands are added per server so they show up straight away."""
        self.tree.copy_global_to(guild=guild)
        try:
            await self.tree.sync(guild=guild)
        except discord.HTTPException as e:
            print(f"  couldn't add commands in {guild.name}: {e}")

    async def on_ready(self):
        print(f"Proxy Scrape Bot v{__version__} is online as {self.user} in {len(self.guilds)} server(s).")
        print(f"Times use this computer's timezone: {getattr(self.tz, 'key', None) or datetime.now(self.tz).strftime('%Z')}")
        for guild in self.guilds:
            await self.sync_guild(guild)
        link = invite_link(self.user.id)
        print(f"\nAdd it to a server with this link:\n{link}\n")
        if self.invite or not self.guilds:
            open_invite(link)
        else:
            print("(To add it to another server later: start it with --invite, or open the link above.)")
        print("Then type /proxy scrape in a checkout channel. Leave this window open while you use the bot.\n")

    async def on_guild_join(self, guild: discord.Guild):
        print(f"Added to {guild.name}")
        await self.sync_guild(guild)


def summary_embed(r: report.Report, channel_name: str, counted: str, scanned, title_day: str) -> discord.Embed:
    colour = 0x3DDC84 if r.rate >= 0.75 else 0xF5B13D if r.rate >= 0.4 else 0xF0505C
    named = [p for p in r.providers if p.name not in (ISP, NO_PROXY)]
    e = discord.Embed(title=f"Proxy Summary - {title_day}", colour=colour)
    e.description = (f"**{r.total}** checkout webhooks • **{r.with_proxy}** with proxy data • "
                     f"**{r.provider_count}** provider{'s' if r.provider_count != 1 else ''} • "
                     f"**{round(r.rate * 100)}%** success")
    if named:
        lines = [f"{i}) {p.name} - {p.total} ({round(p.rate * 100)}%)" for i, p in enumerate(named[:10], 1)]
        if len(named) > 10:
            lines.append(f"…and {len(named) - 10} more")
        e.add_field(name="By provider", value="\n".join(lines), inline=False)
    types: dict = {}
    for a in r.attempts:
        types[a.ptype] = types.get(a.ptype, 0) + 1
    e.add_field(name="By type", value="\n".join(f"• {TYPE_NAMES[k]} - {n}" for k, n in
                                               sorted(types.items(), key=lambda kv: -kv[1])) or "–", inline=False)
    fails = ", ".join(f"{n} {k}" for k, n in r.fails.most_common())
    if fails:
        e.add_field(name="Failed", value=fails, inline=False)
    notes = [f"#{channel_name}", counted, f"{scanned.messages} messages read"]
    if scanned.not_read:
        notes.append(f"{scanned.not_read} from other bots skipped")
    if scanned.capped:
        notes.append("stopped at 50,000 messages")
    e.set_footer(text=" • ".join(notes))
    e.set_image(url="attachment://proxy-timeline.png")
    return e


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class ProxyCommands(app_commands.Group):
    def __init__(self, bot: ProxyBot):
        super().__init__(name="proxy", description="Proxy summaries from checkout webhooks")
        self.bot = bot

    @app_commands.command(name="scrape", description="Read checkout webhooks and post a proxy summary + timeline")
    @app_commands.describe(
        start="First message: a message link or ID, or a date like 2026-10-30, today, yesterday",
        end="Last message (link or ID) or last day (date). Leave empty to read up to now",
        include="Count only successful checkouts, or successes and every failure (default)",
        channel="Channel to read (default: this one, or the channel of a message link)")
    @app_commands.choices(include=[app_commands.Choice(name="success + all fails", value="all"),
                                   app_commands.Choice(name="success only", value="success")])
    async def scrape(self, interaction: discord.Interaction, start: str, end: str | None = None,
                     include: app_commands.Choice[str] | None = None,
                     channel: discord.TextChannel | discord.Thread | None = None):
        tz = self.bot.tz
        try:
            first = read_point(start, tz)
            last = read_point(end, tz, end=True) if end else None
        except BadPoint as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        target = channel or (self.bot.get_channel(first.channel_id) if first.channel_id else None) or interaction.channel
        if first.channel_id and target.id != first.channel_id:
            return await interaction.response.send_message(
                "That start link is a message in another channel. Run the command there, or pick that channel.",
                ephemeral=True)
        mine = target.permissions_for(target.guild.me)
        if not (mine.view_channel and mine.read_message_history):
            return await interaction.response.send_message(
                f"I can't read {target.mention}: give me View Channel and Read Message History there.", ephemeral=True)
        if last and _key(last) <= _key(first):
            return await interaction.response.send_message("The end is before the start.", ephemeral=True)
        if interaction.guild_id in self.bot.busy:
            return await interaction.response.send_message("A scrape is already running in this server.", ephemeral=True)

        include_fails = include is None or include.value == "all"
        counted = "success + all fails" if include_fails else "success only"
        self.bot.busy.add(interaction.guild_id)
        await interaction.response.send_message(f"Scanning {target.mention}…")
        try:
            async def progress(n):
                try:
                    await interaction.edit_original_response(content=f"Scanning {target.mention}… {n:,} messages read")
                except discord.HTTPException:
                    pass

            scanned = await scan(target, first, last, tz, self.bot.user.id, include_fails, progress)
            r = report.build(scanned.attempts)
            if not r.total:
                text = (f"No Valor / Shikari / sniped.gg / Refract checkout webhooks found in {target.mention} "
                        f"for that range ({scanned.messages:,} messages read).")
                return await self._finish(interaction, target, content=text)
            day = (r.first.strftime("%b %d, %Y") if r.first.date() == r.last.date()
                   else f"{r.first:%b %d} - {r.last:%b %d, %Y}")
            png = await asyncio.to_thread(chart.render, r, target.name, counted)
            embed = summary_embed(r, target.name, counted, scanned, day)
            await self._finish(interaction, target, embed=embed,
                               file=discord.File(io.BytesIO(png), filename="proxy-timeline.png"))
        except discord.Forbidden:
            await self._finish(interaction, target, content=f"I lost access to {target.mention} while reading it.")
        except Exception as e:
            print(f"scrape failed: {e!r}")
            await self._finish(interaction, target, content="Something went wrong while scraping. Details are in "
                                                            "the bot's window.")
            raise
        finally:
            self.bot.busy.discard(interaction.guild_id)

    async def _finish(self, interaction, target, content=None, embed=None, file=None):
        """Replace the "Scanning…" message; after 15 minutes Discord no longer allows that, so post a new one."""
        try:
            await interaction.edit_original_response(content=content, embed=embed,
                                                     attachments=[file] if file else [])
        except discord.HTTPException:
            if file:
                file.reset()
            await target.send(content=content or interaction.user.mention, embed=embed, file=file)

    @app_commands.command(name="help", description="How to use /proxy scrape")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "**/proxy scrape** reads checkout webhooks (Valor, Shikari, sniped.gg, Refract) in a channel and posts a "
            "proxy summary with a timeline.\n"
            "• `start`: right-click the first webhook > **Copy Message Link** (or ID), or a date: `2026-10-30`, "
            "`today`, `yesterday`\n"
            "• `end` (optional): the last message, or the last day. Empty = up to now\n"
            "• `include`: success + all fails (default) or success only\n"
            "Only proxy **provider and type** are shown, never proxy logins. Times are in the local time of the "
            "computer running the bot.", ephemeral=True)


def _key(point) -> int:
    """A start / end as a message ID, so a message and a date can be compared."""
    return point.id or discord.utils.time_snowflake(point.when)


def run(token: str, tz, invite: bool = False) -> None:
    ProxyBot(tz, invite).run(token, log_level=logging.WARNING)
