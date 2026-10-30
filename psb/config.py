"""Settings, kept only on this computer: your bot token. Times use this computer's own timezone.

  Windows   %APPDATA%\\ProxyScrapeBot\\config.json
  Mac/Linux ~/.config/proxy-scrape-bot/config.json
A DISCORD_TOKEN environment variable wins over the file. The first start asks for the token (setup()).
"""
import getpass
import json
import os
import sys
from datetime import datetime, tzinfo
from pathlib import Path


def folder() -> Path:
    if sys.platform == "win32" and os.getenv("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ProxyScrapeBot"
    return Path.home() / ".config" / "proxy-scrape-bot"


def path() -> Path:
    return folder() / "config.json"


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data = {}
    if os.getenv("DISCORD_TOKEN"):
        data["token"] = os.environ["DISCORD_TOKEN"].strip()
    return data


def save(data: dict) -> None:
    folder().mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps({"token": data["token"]}, indent=2), encoding="utf-8")


def local_timezone() -> tzinfo:
    """This computer's timezone, with daylight saving (e.g. America/New_York shown as EDT / EST)."""
    try:
        from tzlocal import get_localzone
        return get_localzone()
    except Exception:
        return datetime.now().astimezone().tzinfo   # fixed offset: right for today, no daylight-saving changes


def setup(data: dict, reset_token: bool = False) -> dict:
    """Ask for the token in the console (first start, or after Discord rejected it)."""
    if reset_token or not data.get("token"):
        print("\nProxy Scrape Bot needs YOUR OWN Discord bot token (see the README on GitHub, 'Make your bot').")
        print("Discord Developer Portal > your app > Bot > Reset Token > Copy. It stays on this computer only.\n")
        token = ""
        while not token:
            token = getpass.getpass("Paste your bot token (it won't show while you paste) and press Enter: ").strip()
        data["token"] = token
        save(data)
        print(f"Saved to {path()}\n")
    return data
