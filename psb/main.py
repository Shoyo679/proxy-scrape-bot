"""Start the bot: asks for your token the first time, then stays online while this window is open.

  ProxyScrapeBot.exe            (or: python run.py)
  ProxyScrapeBot.exe --reset    ask for the token again
  ProxyScrapeBot.exe --invite   open the "add to server" page again (it opens by itself while the bot is in no server)
"""
import sys

import discord

from . import bot, config
from .version import __version__


def _pause() -> None:
    """Keep the window open after a problem when started by double-click (the .exe)."""
    if getattr(sys, "frozen", False):
        input("\nPress Enter to close.")


def main() -> int:
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    print(f"Proxy Scrape Bot v{__version__}")
    data = config.setup(config.load(), reset_token="--reset" in sys.argv)
    while True:
        try:
            bot.run(data["token"], config.local_timezone(), invite="--invite" in sys.argv)
            return 0
        except discord.LoginFailure:
            print("\nDiscord rejected that token. Copy a fresh one: Developer Portal > your app > Bot > Reset Token.")
            data = config.setup(data, reset_token=True)
        except discord.PrivilegedIntentsRequired:
            print("\nTurn on MESSAGE CONTENT INTENT for your bot: Developer Portal > your app > Bot > "
                  "Privileged Gateway Intents > Message Content Intent > Save. Then start this again.")
            _pause()
            return 1
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"\nThe bot stopped: {e!r}")
            _pause()
            return 1
