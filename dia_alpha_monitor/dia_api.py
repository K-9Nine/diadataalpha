"""DIA official API collector (api.diadata.org — DIA's *own* data).

This is the most trusted source in the tool: DIA pricing its own token and
reporting its own coverage. Two things make it valuable:

  * the asset quotation is **signed** by DIA, and lets us cross-check the
    CoinGecko market price against what DIA's oracle itself publishes — a
    large divergence is a data-integrity red flag worth surfacing;
  * ``quotedAssets`` / ``exchanges`` are primary-source coverage metrics
    (how many assets DIA prices, how many exchange scrapers feed it, and how
    many are currently active) — a real operational/adoption signal rather
    than a manual guess.

Like every collector, each sub-fetch fails gracefully: a missing piece is
left as ``None`` and noted in ``error``; nothing here ever raises.
"""

from __future__ import annotations

from typing import Optional

from dia_alpha_monitor.http_client import get_json
from dia_alpha_monitor.models import (
    DIA_TOKEN_ETHEREUM,
    DiaOracleSnapshot,
    today_str,
    utcnow,
)

BASE = "https://api.diadata.org/v1"


def fetch_dia_oracle(cache=None) -> DiaOracleSnapshot:
    """Collect DIA's self-reported price + coverage from DIA's own API."""
    snap = DiaOracleSnapshot(date=today_str(), ts=utcnow().isoformat())
    errors: list[str] = []

    # 1. DIA's own signed quotation for the DIA token.
    quote, qerr = get_json(
        f"{BASE}/assetQuotation/Ethereum/{DIA_TOKEN_ETHEREUM}",
        cache=cache,
        cache_source="diadata",
        cache_key="assetQuotation:DIA",
    )
    if qerr or not quote:
        errors.append(f"quotation: {qerr or 'no data'}")
    else:
        snap.dia_price = quote.get("Price")
        snap.dia_price_yesterday = quote.get("PriceYesterday")
        snap.volume_yesterday_usd = quote.get("VolumeYesterdayUSD")
        snap.signature = quote.get("Signature", "") or ""

    # 2. Coverage: how many assets DIA quotes.
    assets, aerr = get_json(
        f"{BASE}/quotedAssets",
        cache=cache,
        cache_source="diadata",
        cache_key="quotedAssets",
    )
    if aerr or assets is None:
        errors.append(f"quotedAssets: {aerr or 'no data'}")
    elif isinstance(assets, list):
        snap.quoted_assets = len(assets)

    # 3. Sources: how many exchange scrapers feed DIA, and how many are active.
    exchanges, eerr = get_json(
        f"{BASE}/exchanges",
        cache=cache,
        cache_source="diadata",
        cache_key="exchanges",
    )
    if eerr or exchanges is None:
        errors.append(f"exchanges: {eerr or 'no data'}")
    elif isinstance(exchanges, list):
        snap.exchange_sources = len(exchanges)
        snap.active_scrapers = sum(1 for e in exchanges if e.get("ScraperActive"))

    snap.error = "; ".join(errors)
    return snap


def price_divergence_pct(
    dia_price: Optional[float], market_price: Optional[float]
) -> Optional[float]:
    """Percent difference of the CoinGecko market price vs DIA's own price.

    Positive => the market price sits above DIA's self-reported price. This is
    a data-integrity / sanity check (do two independent sources agree?), not a
    trading signal. Returns ``None`` if either price is missing or zero.
    """
    if not dia_price or not market_price:
        return None
    return (market_price - dia_price) / dia_price * 100.0
