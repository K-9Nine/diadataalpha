"""RSS/Atom auto-ingestion for the news tracker.

Fetches the feeds in ``config/news_feeds.yaml`` (DIA's blog by default), parses
them with the stdlib XML parser (no new dependency), classifies each item by
keyword, and upserts it into the ``ingested_news`` table — de-duplicated by URL.
The report then merges these with the manually-curated ``config/news.yaml``
(manual entries win on URL conflicts), so curation and automation coexist.

Everything is graceful: a dead/garbled feed is recorded and skipped, never
raising. Keep the feed list to trusted (DIA-official) sources — each item
carries its source so provenance stays visible.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from dia_alpha_monitor.http_client import get_text
from dia_alpha_monitor.models import today_str, utcnow

# Keyword -> category. First match wins (checked in this order).
_CATEGORY_RULES = [
    ("competitor", ("chainlink", "pyth", "redstone", "api3", "chronicle")),
    ("staking", ("staking", "stake", "lasernet", "feeder", "lumina", "apy", "yield")),
    ("RWA", ("rwa", "real-world", "real world", "equit", "stock", "etf", "commodit",
             "bond", "forex", " fx ", "gold", "treasur", "nav", "proof of reserve",
             "reserve", "tokeniz", "stablecoin")),
    ("integration", ("integrat", "partner", "powers", "deploy", "launch", "live on",
                     "oracle for", "brings", "adds")),
]

_MAJOR_MARKERS = ("launch", "mainnet", "first", "unveil", "goes live", "live:")

# CATALYST markers — the thesis-critical signals an upside re-rating actually needs:
# (a) MONETISATION — usage finally flowing to the token (the missing piece today);
# (b) MAJOR ADOPTION — institutional / vault / named large customer;
# (c) GRANT->PAID conversion — free-trial oracles becoming paying customers.
# A match floats the item to the top (impact 5) and tags it [CATALYST] in the report.
_CATALYST_KEYWORDS = (
    # (a) monetisation / value capture
    "fee switch", "fee-switch", "revenue", "revenue share", "buyback", "buy back",
    "buy-back", "burn", "fee distribution", "fee sharing", "monetis", "monetiz",
    "paying customer", "paid plan", "paid tier", "fees from",
    # (b) major / institutional adoption
    "institutional", "tradfi", "asset manager", "blackrock", "vault",
    # (c) grant -> paid conversion
    "grant conversion", "converts to paid", "graduat", "now paying",
)


def is_catalyst(title: str) -> bool:
    """True if a headline matches a thesis-critical catalyst keyword (see above)."""
    t = (title or "").lower()
    return any(k in t for k in _CATALYST_KEYWORDS)


def _classify(title: str, default_impact: int) -> tuple[str, int]:
    t = (title or "").lower()
    category = "DeFi"
    for cat, kws in _CATEGORY_RULES:
        if any(k in t for k in kws):
            category = cat
            break
    impact = default_impact
    if category in ("RWA", "integration"):
        impact += 1
    if any(m in t for m in _MAJOR_MARKERS):
        impact += 1
    if is_catalyst(title):
        impact = 5  # thesis-critical -> always surface at the top
    return category, max(1, min(5, impact))


def _pub_to_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)[:10]


def parse_rss(xml_text: str, source: str, default_impact: int = 3) -> list[dict[str, Any]]:
    """Parse RSS 2.0 / Atom text into news-item dicts. Tolerant of malformed feeds."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    items: list[dict[str, Any]] = []
    # RSS 2.0: channel/item ; Atom: feed/entry
    nodes = root.findall(".//item")
    atom = "{http://www.w3.org/2005/Atom}"
    if not nodes:
        nodes = root.findall(f".//{atom}entry")
    for n in nodes:
        title = n.findtext("title") or n.findtext(f"{atom}title") or ""
        link = n.findtext("link") or ""
        if not link:
            link_el = n.find(f"{atom}link")
            if link_el is not None:
                link = link_el.get("href", "")
        pub = n.findtext("pubDate") or n.findtext(f"{atom}updated") or n.findtext(f"{atom}published")
        title = title.strip()
        link = link.strip()
        if not title or not link:
            continue
        category, impact = _classify(title, default_impact)
        items.append(
            {
                "date": _pub_to_date(pub),
                "title": title,
                "url": link,
                "source": source,
                "category": category,
                "impact_score": impact,
            }
        )
    return items


def fetch_feed(feed: dict, cache=None) -> tuple[list[dict], str]:
    url = feed.get("url", "")
    if not url:
        return [], "no url configured"
    text, err = get_text(url)
    if err or not text:
        return [], err or "no data"
    items = parse_rss(text, feed.get("name", url), int(feed.get("default_impact", 3) or 3))
    return items, ""


def ingest(feeds: list[dict], db) -> dict[str, Any]:
    """Fetch all feeds and upsert items into ``ingested_news`` (dedup by URL)."""
    new = 0
    seen = 0
    errors: list[str] = []
    now = utcnow().isoformat()
    for feed in feeds:
        items, err = fetch_feed(feed)
        if err:
            errors.append(f"{feed.get('name', feed.get('url', '?'))}: {err}")
            continue
        for it in items:
            seen += 1
            cur = db.conn.execute(
                "INSERT OR IGNORE INTO ingested_news"
                "(first_seen, date, title, url, source, category, impact_score)"
                " VALUES (?,?,?,?,?,?,?)",
                (now, it["date"], it["title"], it["url"], it["source"],
                 it["category"], it["impact_score"]),
            )
            if cur.rowcount:
                new += 1
    db.conn.commit()
    return {"new": new, "seen": seen, "errors": errors}


def load_ingested(db) -> list[dict]:
    """Return all ingested news items as plain dicts (news-item shape)."""
    rows = db.conn.execute(
        "SELECT date, title, url, source, category, impact_score FROM ingested_news"
    ).fetchall()
    return [dict(r) for r in rows]
