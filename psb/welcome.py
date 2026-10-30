"""The token window: a dark welcome card (first start) or a "new token" card (Change token / token rejected).

  header   logo, "Welcome to Proxy Scrape Bot", one friendly line
  setup    three numbered steps (left) and "When does the bot work?" (right), links to the Developer Portal and to
           the full guide (the README on GitHub)
  token    a box that shows dots (Show / Hide), a quick check that it looks like a bot token
  buttons  Cancel and Start bot
Same colours as the Proxy Timeline image. Sharp on high-DPI screens (dpi_aware() runs before Tk starts).
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
WIDTH = 900


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


def ask_token(root: tk.Misc, logo_path, icon_path=None, reason: str = "", first: bool = True) -> str | None:
    """Show the card and wait. Returns the token, or None if the window was closed / cancelled."""
    win = tk.Toplevel(root)
    win.title("Proxy Scrape Bot")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    if icon_path:
        try:
            win.iconbitmap(str(icon_path))
        except tk.TclError:
            pass
    scale = win.winfo_fpixels("1i") / 96   # 1.0 at 100 % Windows scaling, 1.5 at 150 %
    px = lambda v: int(v * scale)   # noqa: E731
    wrap = px(WIDTH - 2 * 28)

    outer = tk.Frame(win, bg=BG, padx=px(28), pady=px(20))
    outer.pack(fill="both")

    # header
    head = tk.Frame(outer, bg=BG)
    head.pack(fill="x")
    img = ImageTk.PhotoImage(Image.open(logo_path).resize((px(52), px(52)), Image.LANCZOS))
    logo = tk.Label(head, image=img, bg=BG)
    logo.image = img
    logo.pack(side="left", padx=(0, px(14)))
    titles = tk.Frame(head, bg=BG)
    titles.pack(side="left", fill="x")
    tk.Label(titles, text="Welcome to Proxy Scrape Bot" if first else "Paste a new bot token", bg=BG, fg=INK,
             font=("Segoe UI Semibold", 16)).pack(anchor="w")
    tk.Label(titles, text="Let's connect your own Discord bot. It takes about 3 minutes." if first
             else "Your bot keeps its servers, it just needs the new token.", bg=BG, fg=MUTED,
             font=("Segoe UI", 10)).pack(anchor="w")

    if reason:
        note = tk.Frame(outer, bg="#3a2f17", padx=px(12), pady=px(8))
        note.pack(fill="x", pady=(px(16), 0))
        tk.Label(note, text=reason, bg="#3a2f17", fg=AMBER, font=("Segoe UI", 10), wraplength=wrap - px(24),
                 justify="left").pack(anchor="w")

    # setup steps (left) and when the bot works (right)
    cols = tk.Frame(outer, bg=BG)
    cols.pack(fill="x", pady=(px(18), 0))
    cols.columnconfigure(0, weight=1, uniform="c")
    cols.columnconfigure(1, weight=1, uniform="c")
    col_wrap = (px(WIDTH) - 2 * px(28) - px(14)) // 2 - px(36 + 38)

    def card(column, heading):
        frame = tk.Frame(cols, bg=CARD, padx=px(18), pady=px(14))
        frame.grid(row=0, column=column, sticky="nsew", padx=(0, px(7)) if column == 0 else (px(7), 0))
        tk.Label(frame, text=heading, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(0, px(6)))
        return frame

    def item(parent, mark, mark_colour, title, text):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=px(4))
        badge = tk.Canvas(row, width=px(26), height=px(26), bg=CARD, highlightthickness=0)
        badge.create_oval(1, 1, px(25), px(25), fill=mark_colour, outline="")
        badge.create_text(px(13), px(13), text=mark, fill=INK, font=("Segoe UI Semibold", 10))
        badge.pack(side="left", anchor="n", padx=(0, px(12)))
        texts = tk.Frame(row, bg=CARD)
        texts.pack(side="left", fill="x")
        tk.Label(texts, text=title, bg=CARD, fg=INK, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(texts, text=text, bg=CARD, fg=INK_2, font=("Segoe UI", 10), wraplength=col_wrap,
                 justify="left").pack(anchor="w")

    setup = card(0, "SET UP (ONCE)")
    for i, (title, text) in enumerate([
            ("Create your bot", "Developer Portal > New Application > name it > Create."),
            ("Copy its token", "Bot > Reset Token > Copy, then paste it below."),
            ("Let it read webhooks", "Same page: switch on Message Content Intent > Save."),
            ("Add it to your server", "After Start bot a page opens: pick your server > Authorize "
                                      "(needs Manage Server).")], 1):
        item(setup, str(i), ACCENT, title, text)
    when = card(1, "WHEN DOES THE BOT WORK?")
    for mark, colour, title, text in [
            ("●", "#1f6f45", "While this app is running", "It runs in the background with an icon by the clock. "
                                                          "No window to keep open."),
            ("!", "#6b5418", "Only while your PC is on", "PC off or asleep, or Quit in the icon's menu = bot offline."),
            ("↻", "#2b4f7a", "Start with Windows", "Right-click the icon > Start with Windows: online at every log-in."),
            ("/", ACCENT, "Use it in Discord", "Type /proxy scrape in your checkout webhook channel.")]:
        item(when, mark, colour, title, text)

    links = tk.Frame(outer, bg=BG)
    links.pack(fill="x", pady=(px(12), 0))
    for text, url in (("Open the Developer Portal  ↗", PORTAL), ("Read the full guide  ↗", GUIDE)):
        link = tk.Label(links, text=text, bg=BG, fg="#a996ff", cursor="hand2", font=("Segoe UI Semibold", 10))
        link.pack(side="left", padx=(0, px(22)))
        link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))

    # token box
    tk.Label(outer, text="BOT TOKEN", bg=BG, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(px(14), px(6)))
    box = tk.Frame(outer, bg=FIELD, highlightthickness=px(2), highlightbackground=LINE, highlightcolor=ACCENT)
    box.pack(fill="x")
    value = tk.StringVar()
    entry = tk.Entry(box, textvariable=value, show="•", bg=FIELD, fg=INK, insertbackground=INK, relief="flat",
                     font=("Segoe UI", 11), highlightthickness=0)
    entry.pack(side="left", fill="x", expand=True, padx=px(12), pady=px(9))
    toggle = tk.Label(box, text="Show", bg=FIELD, fg=MUTED, cursor="hand2", font=("Segoe UI Semibold", 9), padx=px(12))
    toggle.pack(side="right")

    def flip(_e=None):
        hidden = entry.cget("show") == "•"
        entry.configure(show="" if hidden else "•")
        toggle.configure(text="Hide" if hidden else "Show")

    toggle.bind("<Button-1>", flip)
    hint = tk.Label(outer, text="🔒  Saved only on this computer. Never share it: it controls your bot.", bg=BG,
                    fg=MUTED, font=("Segoe UI", 9))
    hint.pack(anchor="w", pady=(px(8), 0))

    # buttons
    result: dict = {}

    def start(_e=None):
        token = value.get().strip().strip('"')
        if not looks_like_token(token):
            hint.configure(text="That doesn't look like a bot token. Use Bot > Reset Token > Copy, then paste here.",
                           fg=AMBER)
            box.configure(highlightbackground=AMBER)
            return
        result["token"] = token
        win.destroy()

    bar = tk.Frame(outer, bg=BG)
    bar.pack(fill="x", pady=(px(16), 0))
    _button(bar, "Start bot  →", start, primary=True).pack(side="right")
    _button(bar, "Cancel", win.destroy).pack(side="right", padx=(0, px(10)))
    _button(bar, "Guide  ↗", lambda: webbrowser.open(GUIDE)).pack(side="left")
    win.bind("<Return>", start)
    win.bind("<Escape>", lambda _e: win.destroy())

    win.update_idletasks()
    win.geometry(f"{px(WIDTH)}x{win.winfo_reqheight()}"
                 f"+{(win.winfo_screenwidth() - px(WIDTH)) // 2}+{max(0, (win.winfo_screenheight() - win.winfo_reqheight()) // 3)}")
    entry.focus_force()
    root.wait_window(win)
    return result.get("token")
