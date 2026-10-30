"""A webhook's proxy -> (type, provider).

  type      "resi", "mobile", "isp", or None (no proxy in the webhook)
  provider  the proxy's domain for resi and mobile proxies (e.g. "vaultedproxies"); ISP proxies are raw IPs, so None

Only these two are ever kept. The proxy string itself (host, port, username, password) and your own list label in
front of it ("(My List) host:port:user:pass") are read in memory and thrown away; the label is never used.
"""
import re

from .parse import embed_fields, unspoil

# Proxy domains whose type can't be told from the format alone, e.g. {"someproxies": "isp"}.
# Wealth and Room40 look like ISP (plain username) but are confirmed resi, so they need no entry.
PROXY_TYPE_OVERRIDES: dict[str, str] = {}

PROXY_FIELDS = ("Proxy", "Proxy Details")   # Refract: "Proxy Details" (its "Queue Proxy" is not the checkout's)

_IP = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def proxy_info(raw: str | None) -> tuple[str | None, str | None]:
    """(type, provider) from a proxy string."""
    if not raw:
        return None, None
    raw = unspoil(raw)
    if not raw or raw == "[removed]":
        return None, None
    raw = re.sub(r"^\([^)]*\)\s*", "", raw)  # drop the user's own "(label) " prefix; never used to classify
    host = raw.split(":")[0]
    if _IP.fullmatch(host):
        return "isp", None
    provider = host.split(".")[-2] if "." in host else host
    username = raw.split(":")[2] if raw.count(":") >= 3 else ""
    kind = PROXY_TYPE_OVERRIDES.get(provider)
    if kind is None:
        # Mobile pools are named in the username: "pool-mob2", or a mobile package like Proxy Haus "pkg-hausmob".
        kind = "mobile" if re.search(r"pool-mob|pkg-\w*mob\b", username, re.I) else "resi"
    return kind, provider.lower() if kind in ("resi", "mobile") else None


def from_embed(embed: dict) -> dict:
    """{"type", "provider"} for a raw (not yet cleaned) webhook embed."""
    fields = embed_fields(embed)
    kind, provider = proxy_info(next((fields[f] for f in PROXY_FIELDS if fields.get(f)), None))
    return {"type": kind, "provider": provider}


NO_PROXY = "No proxy data"
ISP = "ISP (no provider name)"


def label(kind: str | None, provider: str | None) -> str:
    """How a proxy is shown: "Vaultedproxies", "Proxy-haus · mobile", "ISP (no provider name)", "No proxy data"."""
    if kind is None:
        return NO_PROXY
    if kind == "isp":
        return ISP
    name = (provider or "unknown provider").capitalize()
    return f"{name} · mobile" if kind == "mobile" else name
