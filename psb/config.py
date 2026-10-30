"""Settings, kept only on this computer: your bot token and timezone.

  Windows   %APPDATA%\\ProxyScrapeBot\\config.json
  Mac/Linux ~/.config/proxy-scrape-bot/config.json
DISCORD_TOKEN / TIMEZONE environment variables win over the file. The first start asks for both (setup()).
"""
import getpass
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/New_York"


def folder() -> Path:
    if sys.platform == "win32" and os.getenv("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ProxyScrapeBot"
    return Path.home() / ".config" / "proxy-scrape-bot"


def path() -> Path:
    return folder() / "config.json"


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if os.getenv("DISCORD_TOKEN"):
        data["token"] = os.environ["DISCORD_TOKEN"].strip()
    if os.getenv("TIMEZONE"):
        data["timezone"] = os.environ["TIMEZONE"].strip()
    data.setdefault("timezone", DEFAULT_TIMEZONE)
    return data


def save(data: dict) -> None:
    folder().mkdir(parents=True, exist_ok=True)
    keep = {k: data[k] for k in ("token", "timezone") if data.get(k)}
    path().write_text(json.dumps(keep, indent=2), encoding="utf-8")


def timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def setup(data: dict, reset_token: bool = False) -> dict:
    """Ask for what's missing in the console (first start, or after Discord rejected the token)."""
    if reset_token or not data.get("token"):
        print("\nProxy Scrape Bot needs YOUR OWN Discord bot token (see the README on GitHub, 'Make your bot').")
        print("Discord Developer Portal > your app > Bot > Reset Token > Copy. It stays on this computer only.\n")
        token = ""
        while not token:
            token = getpass.getpass("Paste your bot token (it won't show while you paste) and press Enter: ").strip()
        data["token"] = token
        if not os.getenv("TIMEZONE"):
            answer = input(f"Your timezone for the chart times [{data.get('timezone', DEFAULT_TIMEZONE)}]: ").strip()
            while answer and not valid_timezone(answer):
                answer = input("Not a timezone name. Examples: America/New_York, Europe/London, Asia/Kolkata: ").strip()
            if answer:
                data["timezone"] = answer
        save(data)
        print(f"Saved to {path()}\n")
    return data
