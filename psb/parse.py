"""Read checkout webhooks from Valor, Shikari, sniped.gg and Refract (fields, outcome, product).

Emails, logins and order numbers are never copied into results.
"""
import html
import re


# Text that only appears in a bot's "is my webhook working?" message.
TEST_MARKERS = (
    "this is a test message from valor",
    "your webhook is configured and working correctly",  # Shikari "Bing Bong"
)



def unspoil(value: str) -> str:
    return value.replace("||", "").strip()


def embed_fields(embed: dict) -> dict[str, str]:
    return {f["name"]: unspoil(f["value"]) for f in embed.get("fields", [])}


def detect_bot(record: dict, embed: dict) -> str | None:
    if (embed.get("author") or {}).get("name") == "Shikari":
        return "shikari"
    footer = (embed.get("footer") or {}).get("text", "")
    if footer.startswith("Prism Technologies"):   # Refract (by Prism); the sender name is the member's own webhook name
        return "refract"
    if footer.startswith("Valor") or record["source_name"].startswith("Valor"):
        return "valor"
    if footer == "sniped.gg" or record["source_name"] == "sniped.gg":
        return "sniped"
    return None


OTHER_SENDER = "other sender"   # not Valor, Shikari, sniped.gg or Refract: skipped, and listed so the owner knows


def is_own_summary(embed: dict) -> bool:
    """Tally's own Drop summary, posted back into a channel Tally watches: skipped silently."""
    footer = (embed.get("footer") or {}).get("text", "")
    return (footer.startswith(("Tally ·", "Archon FAF ·"))   # Drop summaries posted by Tally / Archon FAF
            and " drop · " in embed.get("title", ""))


# Notices from our bots that aren't orders at all: skipped silently, never saved or reported (owner, Oct 24 2026).
IGNORED_TITLES = {"sniped": ("raffle entered",)}


def is_ignored(record: dict, embed: dict) -> bool:
    bot = detect_bot(record, embed)
    title = (embed.get("title") or "").lower()
    return any(t in title for t in IGNORED_TITLES.get(bot, ()))


# Valor's order checker: a later message about an order that was already checked out (docs/WEBHOOK_FORMATS.md).
# "Order Still Good" = not cancelled; "Order Canceled! (Policy - Item Demand)" = cancelled, reason in brackets.
def order_check_kind(bot: str | None, title: str) -> str | None:
    t = title.lower()
    if bot != "valor":
        return None
    if "still good" in t:
        return "good"
    if "order canceled" in t or "order cancelled" in t:
        return "cancelled"
    return None


def parse_order_check(record: dict) -> dict | None:
    """Valor "Order Still Good" -> {"kind": "good", ...}; "Order Canceled!" checks are cancels (parse_checkout)."""
    if not record.get("embeds"):
        return None
    embed = record["embeds"][0]
    title = re.sub(r":[a-z0-9_+-]+:", "", embed.get("title", "")).strip()
    if order_check_kind(detect_bot(record, embed), title) != "good":
        return None
    fields = embed_fields(embed)
    return {"id": record["id"], "day": record["day"], "created_at": record["created_at"],
            "product_name": clean_name(fields.get("Item")), "quantity": parse_quantity(fields.get("Qty")),
            "order_fp": record.get("order_fp")}


def clean_name(value: str | None) -> str | None:
    """Valor's order checker writes "Pok&#233;mon": turn HTML codes back into letters."""
    return html.unescape(value).strip() if value else None


def is_test(embed: dict) -> bool:
    text = f"{embed.get('title', '')} {embed.get('description', '')}".lower()
    if (embed.get("author") or {}).get("name", "").strip().lower().endswith("| refract"):
        return True   # Refract's test webhook: "Successful Checkout | Refract", a sample product and "Test Proxy List"
    return any(marker in text for marker in TEST_MARKERS)


def title_of(bot: str | None, embed: dict) -> str:
    """The message's title without emoji codes. Refract puts it in the author line: "Successful Checkout | Walmart"."""
    raw = (embed.get("author") or {}).get("name", "").split("|")[0] if bot == "refract" else embed.get("title", "")
    return re.sub(r":[a-z0-9_+-]+:", "", raw or "").strip()


def status_of(title: str, bot: str | None = None) -> str:
    t = title.lower()
    if "review hold" in t:
        return "hold"
    if "checked out" in t or "successful checkout" in t:
        return "success"
    if "cancel" in t:
        return "cancelled"
    if "declined" in t:   # Valor's "Card Declined!" too (owner, v0.5.26: back to a decline after v0.5.25)
        return "declined"
    if "error" in t or "failed" in t:
        return "error"
    # A title we have never seen (e.g. a bot renamed "Checked Out!"). Not guessed: it is left out of the
    # numbers and listed in the "unrecognised" report until parse.py learns it.
    return "unknown"



def safe_parse(record: dict) -> tuple[dict | None, bool]:
    """(checkout or None, failed). One odd webhook must never stop an update or the dashboard."""
    try:
        return parse_checkout(record), False
    except Exception:
        return None, True


def unrecognised_reason(record: dict) -> str | None:
    """Why a saved webhook was left out, or None if it was used or needs no mention (test webhooks, Tally's own
    summaries, messages without an embed).
      "other sender"   from anything but Valor, Shikari, sniped.gg or Refract: only those four are read (skipped, listed)
      "no fields" / "unknown title" / "read error"   one of the three, in a format parse.py can't read yet"""
    if record.get("skipped"):   # another sender: only who/when/where was saved (privacy.prepare)
        return OTHER_SENDER
    if safe_parse(record)[1]:
        return "read error"
    embed = record["embeds"][0] if record.get("embeds") else {}
    if not embed:
        return None
    bot = detect_bot(record, embed)
    if is_test(embed) or is_own_summary(embed) or is_ignored(record, embed):
        return None
    if order_check_kind(bot, title_of(bot, embed)) == "good":
        return None   # read by parse_order_check
    if bot is None:
        return OTHER_SENDER
    if not embed_fields(embed):
        return "no fields"
    if status_of(title_of(bot, embed)) == "unknown":
        return "unknown title"
    return None


def notice_title(record: dict, reason: str) -> str:
    """How a left-out webhook is grouped in reports: by title for our bots, by sender only for other senders."""
    if reason == OTHER_SENDER:
        return ""
    return ((record["embeds"][0].get("title") if record.get("embeds") else None) or "(no title)")[:80]


def parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def parse_quantity(value: str | None) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else 1  # sniped.gg sometimes leaves it out


PLACEHOLDERS = {"", "—", "-", "UNKNOWN", "N/A"}


def clean_store(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s*\(.*?\)\s*$", "", value)  # "Target (Checkout)" -> "Target"
    return re.sub(r"\s+US$", "", value).strip()   # "Walmart US" -> "Walmart"


def id_from_url(url: str) -> str | None:
    """Target: /A-<TCIN>; Walmart: /ip/<slug>/<id> or /ip/<id>."""
    match = re.search(r"/A-(\d+)", url) or re.search(r"/ip/(?:[^/]*/)?(\d+)", url)
    return match.group(1) if match else None


def _product(bot: str, embed: dict, fields: dict) -> tuple[str | None, str | None]:
    """(product_id, product_name)"""
    if bot == "shikari":
        match = re.search(r"\[\*\*(.+?)\*\*\]\((\S+?)\)", embed.get("description", ""))
        return (id_from_url(match.group(2)), match.group(1)) if match else (None, None)
    product = fields.get("Product") or ""
    if bot in ("valor", "refract"):
        match = re.match(r"\[(?:\((\S+)\)\s*)?(.+?)\]\((\S+?)\)", product)  # "[(SKU) Name](url)" or "[Name](url)"
        if match:
            return match.group(1) or id_from_url(match.group(3)), clean_name(match.group(2))
    sku = fields.get("SKU", "")
    return (None if sku in PLACEHOLDERS else sku), (None if product in PLACEHOLDERS else product)


def _author_store(bot: str, embed: dict) -> str | None:
    """Refract names the store after the "|" in the author line."""
    name = (embed.get("author") or {}).get("name", "")
    return name.split("|", 1)[1].strip() if bot == "refract" and "|" in name else None


def _kept(value: str | None) -> str | None:
    """None for empty or removed-for-privacy values (see privacy.py)."""
    return None if not value or value == "[removed]" else value


def parse_checkout(record: dict) -> dict | None:
    """A saved message -> checkout record, or None if it isn't a checkout webhook (or is a test)."""
    if not record.get("embeds"):
        return None
    embed = record["embeds"][0]
    bot = detect_bot(record, embed)
    if bot is None or is_test(embed) or is_ignored(record, embed):
        return None
    fields = embed_fields(embed)
    if not fields:
        return None

    title = title_of(bot, embed)   # emoji codes like :warning: dropped
    if status_of(title) == "unknown":
        return None   # reported by unrecognised_reason() instead of being guessed
    product_id, product_name = _product(bot, embed, fields)
    check = order_check_kind(bot, title)
    if check == "good":
        return None   # not a checkout: an order check (parse_order_check)
    if check == "cancelled":   # Valor's order checker: product name in "Item", quantity in "Qty", reason in brackets
        product_name = clean_name(fields.get("Item"))
        if (bracket := re.search(r"\(([^)]*)\)", title)):
            fields.setdefault("Reason", bracket.group(1))
    reason = fields.get("Reason")
    if reason is None and ":" in title:
        reason = title.split(":", 1)[1].strip()
    if reason:
        reason = re.sub(r"^Policy\s*-\s*", "", reason)  # sniped "Policy - Item Demand" = Shikari "Item Demand"

    return {
        "id": record["id"],
        "day": record["day"],
        "created_at": record["created_at"],
        "bot": bot,
        "store": clean_store(fields.get("Site") or fields.get("Store") or _author_store(bot, embed)),
        "status": status_of(title, bot),
        "reason": reason,
        "product_id": product_id,
        "product_name": product_name,
        "price": parse_price(fields.get("Price")),
        "price_source": "webhook" if parse_price(fields.get("Price")) is not None else None,
        "quantity": parse_quantity(fields.get("Quantity") or fields.get("Qty")),
        "mode": None if fields.get("Mode") in PLACEHOLDERS else fields.get("Mode"),   # Valor: Default / Shipping
        "order_check": check is not None,   # a later cancel from Valor's order checker, not a checkout attempt
        "profile": _kept(next(iter((fields.get("Profile") or "").splitlines()), "").strip()),
        "order_id": _kept(fields.get("Order Number") or fields.get("Order ID")),
        "order_fp": record.get("order_fp"),
        "channel_id": record["channel_id"],
        "jump_url": record["jump_url"],
    }
