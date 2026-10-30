"""The Windows app: the bot runs in the background with an icon by the clock, no console window.

  First start   a small window asks for your bot token (with a button to the Developer Portal)
  Tray icon     right-click: status, Add to server, Open log, Start with Windows, Change token, Quit
  Problems      a wrong token or Message Content Intent switched off show a message and how to fix it
Only one copy runs at a time (a second start just says it's already running). Everything the bot prints goes to
bot.log next to config.json (%APPDATA%\\ProxyScrapeBot).

Threads: Tk (dialogs) runs on the main thread, the tray icon on its own thread, the bot on its own asyncio loop.
Tray clicks are handed to the main thread through a queue.
"""
import asyncio
import os
import queue
import socket
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import messagebox

import discord
import pystray
from PIL import Image

from . import bot, config, welcome
from .version import __version__

LOCK_PORT = 47621   # held while the app runs, so a second copy can tell
PORTAL = "https://discord.com/developers/applications"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ProxyScrapeBot"
NAME = "Proxy Scrape Bot"


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def log_path() -> Path:
    return config.folder() / "bot.log"


def single_instance() -> socket.socket | None:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
        return lock
    except OSError:
        return None


# --- Start with Windows (HKCU Run key: only this user, no admin needed) ---
def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve().parent.parent / "run.py"}" --tray'


def startup_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
            return True
    except OSError:
        return False


def set_startup(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except OSError:
                pass


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.jobs: queue.Queue = queue.Queue()
        self.data = config.load()
        self.client: bot.ProxyBot | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.status = "Starting…"
        self.announced = False
        self.guide_next = False   # show the "How to use" page once the bot is online (after every new token)
        self.guide_open = False
        self.icon = pystray.Icon("ProxyScrapeBot", Image.open(asset("icon.png")), NAME, self.menu())

    # --- main-thread helpers ---
    def later(self, fn) -> None:
        """Run fn on the Tk thread (from the tray or bot threads)."""
        self.jobs.put(fn)

    def _poll(self) -> None:
        while not self.jobs.empty():
            try:
                self.jobs.get_nowait()()
            except Exception:
                traceback.print_exc()
        self.root.after(150, self._poll)

    def ask_token(self, reason: str = "") -> str | None:
        """The token window (welcome.py). None if closed / cancelled."""
        return welcome.ask_token(self.root, asset("icon.png"), asset("icon.ico"), reason=reason,
                                 first=not self.data.get("token"))

    # --- the bot ---
    def start_bot(self) -> None:
        self.status = "Connecting…"
        self.icon.update_menu()
        self.thread = threading.Thread(target=self._run_bot, daemon=True)
        self.thread.start()

    def _run_bot(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.client = bot.ProxyBot(config.local_timezone(), on_status=self._online)
        try:
            loop.run_until_complete(self.client.start(self.data["token"]))
        except discord.LoginFailure:
            self.later(self.bad_token)
        except discord.PrivilegedIntentsRequired:
            self.later(self.intent_off)
        except Exception as e:
            traceback.print_exc()
            self.later(lambda: self.problem(f"The bot stopped: {e}"))
        finally:
            if not self.client.is_closed():
                loop.run_until_complete(self.client.close())
            loop.close()
            self.loop = None
            if not self.status.startswith("Online"):
                return
            self.status = "Offline"
            self.icon.update_menu()

    def stop_bot(self) -> None:
        if self.loop and self.client and not self.client.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self.client.close(), self.loop).result(10)
            except Exception:
                pass
        if self.thread:
            self.thread.join(10)

    def _online(self, client: bot.ProxyBot) -> None:   # bot thread
        n = len(client.guilds)
        self.status = f"Online as {client.user} · {n} server{'s' if n != 1 else ''}"
        self.icon.update_menu()
        if not self.announced:
            self.announced = True
            self.icon.notify("Online. Click this icon by the clock for How to use, right-click for options.", NAME)
        if self.guide_next:
            self.guide_next = False
            self.later(self.how_to_use)

    # --- problems ---
    def bad_token(self) -> None:
        self.status = "Token rejected"
        self.icon.update_menu()
        self.change_token("Discord rejected that token. Copy a fresh one (Bot > Reset Token) and paste it here.")

    def intent_off(self) -> None:
        self.status = "Message Content Intent is off"
        self.icon.update_menu()
        webbrowser.open(PORTAL)
        if messagebox.askretrycancel(NAME, "Switch on MESSAGE CONTENT INTENT for your bot:\nDeveloper Portal > your app "
                                           "> Bot > Privileged Gateway Intents > Message Content Intent > Save Changes."
                                           "\n\nThen press Retry."):
            self.start_bot()

    def problem(self, text: str) -> None:
        self.status = "Stopped (see log)"
        self.icon.update_menu()
        messagebox.showerror(NAME, f"{text}\n\nDetails: {log_path()}")

    # --- tray menu ---
    def menu(self) -> pystray.Menu:
        item = pystray.MenuItem
        return pystray.Menu(
            item(lambda _: self.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("How to use", lambda: self.later(self.how_to_use), default=True),   # also a left-click on the icon
            item("Add to server", lambda: self.later(self.add_to_server)),
            item("Start with Windows", lambda: self.later(self.toggle_startup), checked=lambda _: startup_enabled()),
            item("Change token…", lambda: self.later(self.change_token)),
            item("Open log", lambda: os.startfile(log_path())),
            pystray.Menu.SEPARATOR,
            item("Quit", lambda: self.later(self.quit)),
        )

    def add_to_server(self) -> None:
        if self.client and self.client.user:
            bot.open_invite(bot.invite_link(self.client.user.id))
        else:
            messagebox.showinfo(NAME, "The bot isn't online yet, so its invite link isn't known. Try again in a moment.")

    def how_to_use(self) -> None:
        """Page 2 (welcome.ready): opened after every new token and from the tray icon."""
        if self.guide_open:
            return
        self.guide_open = True
        online = self.client is not None and self.client.user is not None and not self.client.is_closed()
        try:
            welcome.ready(self.root, asset("icon.png"), asset("icon.ico"),
                          str(self.client.user) if online else None, len(self.client.guilds) if online else 0,
                          self.add_to_server, startup_enabled(), self._set_startup)
        finally:
            self.guide_open = False

    def _set_startup(self, on: bool) -> None:
        set_startup(on)
        self.icon.update_menu()

    def toggle_startup(self) -> None:
        set_startup(not startup_enabled())
        self.icon.update_menu()

    def change_token(self, reason: str = "") -> None:
        token = self.ask_token(reason)
        if not token:
            if not self.status.startswith("Online"):
                self.quit()
            return
        self.data["token"] = token
        config.save(self.data)
        self.guide_next = True
        self.stop_bot()
        self.start_bot()

    def quit(self) -> None:
        self.status = "Quitting"
        self.stop_bot()
        self.icon.stop()
        self.root.destroy()

    def run(self) -> int:
        if not self.data.get("token"):
            token = self.ask_token()
            if not token:
                return 0
            self.data["token"] = token
            config.save(self.data)
            self.guide_next = True
        self.icon.run_detached()
        self.start_bot()
        self.root.after(150, self._poll)
        self.root.mainloop()
        return 0


def main() -> int:
    config.folder().mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(log_path(), "a", encoding="utf-8", errors="replace", buffering=1)
    print(f"\n--- {NAME} v{__version__} started ---")
    welcome.dpi_aware()
    lock = single_instance()
    if lock is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(NAME, f"{NAME} is already running: look for its icon by the clock (you may need to "
                                  "click the ^ arrow).")
        return 0
    return App().run()
