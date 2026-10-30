"""The app's two windows, in the chart's colours.

  ask_token()   page 1: welcome (or "Paste a new bot token"), three set-up steps, the token box (Show / Hide, a quick
                check that it looks like a bot token), Guide / Cancel / Start bot
  ready()       page 2, once the bot is online the first time: "You're all set", add it to your server, how to use
                /proxy scrape, things to keep in mind, a Start with Windows tick, Guide / Got it
Links open the Developer Portal or the full guide (the README on GitHub). Sharp on high-DPI screens (dpi_aware() runs
before Tk starts).
"""
import ctypes
import sys
import tkinter as tk
import webbrowser

from PIL import Image, ImageTk

BG, CARD, FIELD, LINE = "#18181b", "#232327", "#2c2c31", "#3a3a41"
INK, INK_2, MUTED = "#f2f2f4", "#c4c4cc", "#8a8a94"
ACCENT, ACCENT_HOVER, GREEN, AMBER = "#7c5cff", "#6a4af0", "#36d77d", "#f5a524"
PORTAL = "https://discord.com/developers/applications"
GUIDE = "https://github.com/Shoyo679/proxy-scrape-bot#readme"   # the README: full setup guide
WIDTH = 600         # page 1
READY_WIDTH = 900   # page 2 (two columns)


def dpi_aware() -> None:
    """Tell Windows we draw at the real screen scale, so text isn't blurry or cut off at 125-150% scaling."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def looks_like_token(text: str) -> bool:
    """Bot tokens are three dot-separated parts, about 70 characters."""
    parts = text.split(".")
    return len(parts) == 3 and all(parts) and len(text) >= 50 and " " not in text


def _button(parent, text, command, primary=False):
    bg, hover = (ACCENT, ACCENT_HOVER) if primary else (FIELD, LINE)
    b = tk.Label(parent, text=text, bg=bg, fg=INK, padx=18, pady=8, cursor="hand2",
                 font=("Segoe UI Semibold", 10))
    b.bind("<Button-1>", lambda _e: command())
    b.bind("<Enter>", lambda _e: b.configure(bg=hover))
    b.bind("<Leave>", lambda _e: b.configure(bg=bg))
    return b


class _Window:
    """A dark Toplevel with px() for screen scaling and the shared pieces (header, notes, cards, items, links)."""

    def __init__(self, root, icon_path, width):
        self.root = root
        self.win = win = tk.Toplevel(root)
        win.title("Proxy Scrape Bot")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        if icon_path:
            try:
                win.iconbitmap(str(icon_path))
            except tk.TclError:
                pass
        self.scale = win.winfo_fpixels("1i") / 96   # 1.0 at 100 % Windows scaling, 1.5 at 150 %
        self.width = width
        self.outer = tk.Frame(win, bg=BG, padx=self.px(28), pady=self.px(22))
        self.outer.pack(fill="both")

    def px(self, v) -> int:
        return int(v * self.scale)

    def header(self, logo_path, title, subtitle):
        head = tk.Frame(self.outer, bg=BG)
        head.pack(fill="x")
        img = ImageTk.PhotoImage(Image.open(logo_path).resize((self.px(52), self.px(52)), Image.LANCZOS))
        logo = tk.Label(head, image=img, bg=BG)
        logo.image = img
        logo.pack(side="left", padx=(0, self.px(14)))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", fill="x")
        tk.Label(titles, text=title, bg=BG, fg=INK, font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(titles, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

    def note(self, text, colour=AMBER, bg="#3a2f17"):
        box = tk.Frame(self.outer, bg=bg, padx=self.px(12), pady=self.px(8))
        box.pack(fill="x", pady=(self.px(16), 0))
        tk.Label(box, text=text, bg=bg, fg=colour, font=("Segoe UI", 10), justify="left",
                 wraplength=self.px(self.width - 2 * 28 - 24)).pack(anchor="w")

    def card(self, parent, heading, column=None):
        frame = tk.Frame(parent, bg=CARD, padx=self.px(18), pady=self.px(14))
        if column is None:
            frame.pack(fill="x", pady=(self.px(18), 0))
        else:
            frame.grid(row=0, column=column, sticky="nsew",
                       padx=(0, self.px(7)) if column == 0 else (self.px(7), 0))
        tk.Label(frame, text=heading, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(
            anchor="w", pady=(0, self.px(6)))
        return frame

    def item(self, parent, mark, mark_colour, title, text, wrap):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=self.px(4))
        badge = tk.Canvas(row, width=self.px(26), height=self.px(26), bg=CARD, highlightthickness=0)
        badge.create_oval(1, 1, self.px(25), self.px(25), fill=mark_colour, outline="")
        badge.create_text(self.px(13), self.px(13), text=mark, fill=INK, font=("Segoe UI Semibold", 10))
        badge.pack(side="left", anchor="n", padx=(0, self.px(12)))
        texts = tk.Frame(row, bg=CARD)
        texts.pack(side="left", fill="x")
        tk.Label(texts, text=title, bg=CARD, fg=INK, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(texts, text=text, bg=CARD, fg=INK_2, font=("Segoe UI", 10), wraplength=wrap,
                 justify="left").pack(anchor="w")

    def link(self, parent, text, url, bg=BG):
        label = tk.Label(parent, text=text, bg=bg, fg="#a996ff", cursor="hand2", font=("Segoe UI Semibold", 10))
        label.bind("<Button-1>", lambda _e: webbrowser.open(url))
        return label

    def show(self, focus=None):
        win = self.win
        win.update_idletasks()
        w, h = self.px(self.width), win.winfo_reqheight()
        win.geometry(f"{w}x{h}+{(win.winfo_screenwidth() - w) // 2}+{max(0, (win.winfo_screenheight() - h) // 3)}")
        if focus is not None:
            focus.focus_force()
        self.root.wait_window(win)


def ask_token(root: tk.Misc, logo_path, icon_path=None, reason: str = "", first: bool = True) -> str | None:
    """Page 1. Returns the token, or None if the window was closed / cancelled."""
    w = _Window(root, icon_path, WIDTH)
    px = w.px
    w.header(logo_path, "Welcome to Proxy Scrape Bot" if first else "Paste a new bot token",
             "Let's connect your own Discord bot. It takes about 3 minutes." if first
             else "Your bot keeps its servers, it just needs the new token.")
    if reason:
        w.note(reason)
    steps = w.card(w.outer, "SET UP YOUR BOT (ONCE)")
    wrap = px(WIDTH - 2 * 28 - 36 - 38)
    for i, (title, text) in enumerate([
            ("Create your bot", "Discord Developer Portal > New Application > give it a name > Create."),
            ("Copy its token", "Left menu Bot > Reset Token > Copy, then paste it below."),
            ("Let it read webhooks", "Same page: switch on Message Content Intent > Save Changes.")], 1):
        w.item(steps, str(i), ACCENT, title, text, wrap)
    w.link(steps, "Open the Developer Portal  ↗", PORTAL, bg=CARD).pack(anchor="w", padx=(px(38), 0),
                                                                       pady=(px(6), 0))

    tk.Label(w.outer, text="BOT TOKEN", bg=BG, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(
        anchor="w", pady=(px(18), px(6)))
    box = tk.Frame(w.outer, bg=FIELD, highlightthickness=px(2), highlightbackground=LINE, highlightcolor=ACCENT)
    box.pack(fill="x")
    value = tk.StringVar()
    entry = tk.Entry(box, textvariable=value, show="•", bg=FIELD, fg=INK, insertbackground=INK, relief="flat",
                     font=("Segoe UI", 11), highlightthickness=0)
    entry.pack(side="left", fill="x", expand=True, padx=px(12), pady=px(9))
    toggle = tk.Label(box, text="Show", bg=FIELD, fg=MUTED, cursor="hand2", font=("Segoe UI Semibold", 9),
                      padx=px(12))
    toggle.pack(side="right")

    def flip(_e=None):
        hidden = entry.cget("show") == "•"
        entry.configure(show="" if hidden else "•")
        toggle.configure(text="Hide" if hidden else "Show")

    toggle.bind("<Button-1>", flip)
    hint = tk.Label(w.outer, text="🔒  Saved only on this computer. Never share it: it controls your bot.", bg=BG,
                    fg=MUTED, font=("Segoe UI", 9))
    hint.pack(anchor="w", pady=(px(8), 0))

    result: dict = {}

    def start(_e=None):
        token = value.get().strip().strip('"')
        if not looks_like_token(token):
            hint.configure(text="That doesn't look like a bot token. Use Bot > Reset Token > Copy, then paste here.",
                           fg=AMBER)
            box.configure(highlightbackground=AMBER)
            return
        result["token"] = token
        w.win.destroy()

    bar = tk.Frame(w.outer, bg=BG)
    bar.pack(fill="x", pady=(px(18), 0))
    _button(bar, "Start bot  →", start, primary=True).pack(side="right")
    _button(bar, "Cancel", w.win.destroy).pack(side="right", padx=(0, px(10)))
    _button(bar, "Guide  ↗", lambda: webbrowser.open(GUIDE)).pack(side="left")
    w.win.bind("<Return>", start)
    w.win.bind("<Escape>", lambda _e: w.win.destroy())
    w.show(entry)
    return result.get("token")


def ready(root: tk.Misc, logo_path, icon_path, bot_name: str | None, servers: int, add_to_server,
          startup_on: bool, set_startup) -> None:
    """Page 2: how to use it and what to keep in mind. Opens after every new token (once the bot is online) and from
    the tray icon (How to use). bot_name None = the bot isn't online right now."""
    w = _Window(root, icon_path, READY_WIDTH)
    px = w.px
    w.header(logo_path, "You're all set!" if bot_name else "How to use Proxy Scrape Bot",
             f"Proxy Scrape Bot is online as {bot_name}." if bot_name else "")
    if not bot_name:
        w.note("The bot isn't online right now. Check its status: right-click the icon by the clock.")
    elif servers:
        w.note(f"It's in {servers} server{'s' if servers != 1 else ''}. Add it to another one any time: right-click "
               "the icon by the clock > Add to server.", GREEN, "#17301f")
    else:
        w.note("Next: add it to your server. A page just opened in your browser: pick your server > Continue > "
               "Authorize (you need Manage Server there). Didn't open? Use Add to server below.")

    cols = tk.Frame(w.outer, bg=BG)
    cols.pack(fill="x", pady=(px(18), 0))
    cols.columnconfigure(0, weight=1, uniform="c")
    cols.columnconfigure(1, weight=1, uniform="c")
    wrap = (px(READY_WIDTH) - 2 * px(28) - px(14)) // 2 - px(36 + 38)
    use = w.card(cols, "HOW TO USE IT", column=0)
    for i, (title, text) in enumerate([
            ("Go to your checkout channel", "Where Valor, Shikari, sniped.gg or Refract post their webhooks."),
            ("Type /proxy scrape", "start: right-click the first webhook > Copy Message Link and paste it. Or a "
                                   "date: 2026-10-30, today, yesterday."),
            ("Optional extras", "end: the last message or day (empty = up to now). include: success only."),
            ("Get your summary", "The bot posts the proxy summary and the Proxy Timeline chart in the channel.")],
            1):
        w.item(use, str(i), ACCENT, title, text, wrap)
    keep = w.card(cols, "KEEP IN MIND", column=1)
    for mark, colour, title, text in [
            ("●", "#1f6f45", "It runs in the background", "Icon by the clock (click ^ if hidden). Right-click it for "
                                                          "Add to server, Change token, Quit."),
            ("!", "#6b5418", "Online only while your PC is on", "PC off or asleep, or Quit = the bot is offline and "
                                                                "/proxy scrape won't answer."),
            ("↺", "#2b4f7a", "Past drops work too", "It reads the channel's history: the bot only has to be online "
                                                    "when you run the command."),
            ("✓", "#3a3a41", "Private", "Only proxy provider and type are shown, never proxy logins. Nothing is saved "
                                      "or sent anywhere else.")]:
        w.item(keep, mark, colour, title, text, wrap)

    bar = tk.Frame(w.outer, bg=BG)
    bar.pack(fill="x", pady=(px(18), 0))
    startup = tk.BooleanVar(value=startup_on)
    tk.Checkbutton(bar, text="  Start with Windows (online every time you log in)", variable=startup,
                   command=lambda: set_startup(startup.get()), bg=BG, fg=INK, selectcolor=FIELD, activebackground=BG,
                   activeforeground=INK, font=("Segoe UI", 10), cursor="hand2").pack(side="left")
    _button(bar, "Got it", w.win.destroy, primary=True).pack(side="right")
    _button(bar, "Guide  ↗", lambda: webbrowser.open(GUIDE)).pack(side="right", padx=(0, px(10)))
    if bot_name:
        _button(bar, "Add to server", add_to_server).pack(side="right", padx=(0, px(10)))
    w.win.bind("<Return>", lambda _e: w.win.destroy())
    w.win.bind("<Escape>", lambda _e: w.win.destroy())
    w.show()
