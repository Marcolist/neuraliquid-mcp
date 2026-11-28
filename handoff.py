"""Public campaign fields only. Never fetch the URL supplied by an agent."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

ORIGIN = "https://futurecast.ml85.xyz"
FEED = "/api/v1/x402/signals/patterns"
SNAPSHOT = "/api/v1/x402/signals/btc-eth-snapshot"
FIELDS = {"ref": r"[A-Za-z0-9_-]{1,24}", "utm_source": r"[a-z0-9-]{1,40}", "via": r"watch"}


def public_tags(link=None, *, resource=FEED):
    if not link:
        return {"utm_source": "mcp"}
    url = urlsplit(link)
    if (len(link) > 400 or url.scheme != "https" or url.netloc != "futurecast.ml85.xyz"
            or url.path not in ("/", "/preview", "/quickstart", FEED, resource)
            or url.fragment not in ("", "wallet", "preview", "agent-preview")):
        raise ValueError("Use a supported FutureCast offer or preview link.")
    tags = {}
    for key, value in parse_qsl(url.query, keep_blank_values=True, strict_parsing=True):
        if key in tags or key not in FIELDS or not re.fullmatch(FIELDS[key], value):
            raise ValueError("Invalid or duplicate campaign field.")
        tags[key] = value
    tags.setdefault("utm_source", "mcp")
    return tags


def checkout_link(tags):
    return ORIGIN + "/quickstart?" + urlencode(tags) + "#wallet"
