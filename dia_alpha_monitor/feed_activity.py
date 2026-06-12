"""Daily DIA feed-coverage tracker, split by asset class (DIA's own API).

Polls ``api.diadata.org`` for the list of quoted assets and exchange sources,
then snapshots:
  * total feeds (assets DIA prices),
  * a best-effort RWA vs crypto split,
  * the number of distinct blockchains covered,
  * the number of active exchange scrapers.

Tracking these daily turns coverage *growth* into a signal.

HONESTY NOTE on the RWA split: the free REST ``/v1/quotedAssets`` endpoint is
crypto-token-centric (assets are keyed by on-chain address + blockchain). DIA's
full RWA / xReal catalogue (stocks, ETFs, commodities, FX — 20,000+ assets) is
*not* enumerated there, so ``rwa_feeds`` only counts entries on non-crypto
"blockchains" that the public endpoint exposes (e.g. ``Fiat``). It is therefore
a floor, not the true RWA total. The marker set below is easy to extend if a
richer endpoint becomes available.
"""

from __future__ import annotations

from dia_alpha_monitor.http_client import get_json
from dia_alpha_monitor.models import FeedActivitySnapshot, today_str, utcnow

BASE = "https://api.diadata.org/v1"

# "Blockchain" values in quotedAssets that denote real-world (non-crypto) feeds.
# Lower-cased for comparison. Extend as DIA surfaces more RWA asset classes.
RWA_BLOCKCHAIN_MARKERS = {
    "fiat",
    "forex",
    "foreignexchange",
    "stock",
    "stocks",
    "equity",
    "equities",
    "commodity",
    "commodities",
    "etf",
    "bond",
    "bonds",
}


def classify_assets(assets: list[dict]) -> dict[str, int]:
    """Split a quotedAssets list into RWA vs crypto and count blockchains."""
    rwa = 0
    blockchains: set[str] = set()
    for a in assets:
        chain = (a.get("Asset", {}) or {}).get("Blockchain", "") or ""
        blockchains.add(chain)
        if chain.lower() in RWA_BLOCKCHAIN_MARKERS:
            rwa += 1
    total = len(assets)
    return {
        "total_feeds": total,
        "rwa_feeds": rwa,
        "crypto_feeds": total - rwa,
        "n_blockchains": len(blockchains),
    }


def fetch_feed_activity(cache=None) -> FeedActivitySnapshot:
    """Snapshot current DIA feed coverage. Graceful on partial failure."""
    snap = FeedActivitySnapshot(date=today_str(), ts=utcnow().isoformat())
    errors: list[str] = []

    assets, aerr = get_json(
        f"{BASE}/quotedAssets",
        cache=cache,
        cache_source="diadata",
        cache_key="quotedAssets",
    )
    if aerr or not isinstance(assets, list):
        errors.append(f"quotedAssets: {aerr or 'no data'}")
    else:
        counts = classify_assets(assets)
        snap.total_feeds = counts["total_feeds"]
        snap.rwa_feeds = counts["rwa_feeds"]
        snap.crypto_feeds = counts["crypto_feeds"]
        snap.n_blockchains = counts["n_blockchains"]

    exchanges, eerr = get_json(
        f"{BASE}/exchanges",
        cache=cache,
        cache_source="diadata",
        cache_key="exchanges",
    )
    if eerr or not isinstance(exchanges, list):
        errors.append(f"exchanges: {eerr or 'no data'}")
    else:
        snap.active_sources = sum(1 for e in exchanges if e.get("ScraperActive"))

    snap.error = "; ".join(errors)
    return snap
