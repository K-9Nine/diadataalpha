"""CoinGecko collector (free, no API key required in v1).

We use the public ``/coins/markets`` endpoint, which returns price, market
cap, volume, supply, FDV and several price-change percentages in one call.
If an optional ``COINGECKO_API_KEY`` is present we pass it through, but it
is never required.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from dia_alpha_monitor.http_client import get_json
from dia_alpha_monitor.models import (
    CompetitorSnapshot,
    MarketSnapshot,
    today_str,
    utcnow,
)

BASE = "https://api.coingecko.com/api/v3"


def _params(ids: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "vs_currency": "usd",
        "ids": ids,
        "price_change_percentage": "24h,7d,30d",
        "sparkline": "false",
    }
    key = os.environ.get("COINGECKO_API_KEY")
    if key:
        params["x_cg_demo_api_key"] = key
    return params


def _row_for(data: list[dict], coingecko_id: str) -> Optional[dict]:
    for row in data or []:
        if row.get("id") == coingecko_id:
            return row
    return None


def fetch_market(coingecko_id: str, cache=None) -> tuple[MarketSnapshot, str]:
    """Fetch a DIA market snapshot. Returns (snapshot, error)."""
    data, err = get_json(
        f"{BASE}/coins/markets",
        params=_params(coingecko_id),
        cache=cache,
        cache_source="coingecko",
        cache_key=f"markets:{coingecko_id}",
    )
    snap = MarketSnapshot(date=today_str(), ts=utcnow().isoformat())
    if err or not data:
        snap.stale = 1
        return snap, err or "no data returned"

    row = _row_for(data, coingecko_id)
    if row is None:
        snap.stale = 1
        return snap, f"id '{coingecko_id}' not found in response"

    snap.price = row.get("current_price")
    snap.market_cap = row.get("market_cap")
    snap.volume_24h = row.get("total_volume")
    snap.circulating_supply = row.get("circulating_supply")
    snap.total_supply = row.get("total_supply") or row.get("max_supply")
    snap.fdv = row.get("fully_diluted_valuation")
    snap.change_1d = row.get("price_change_percentage_24h_in_currency")
    snap.change_7d = row.get("price_change_percentage_7d_in_currency")
    snap.change_30d = row.get("price_change_percentage_30d_in_currency")
    return snap, ""


def fetch_market_chart(coingecko_id: str, days: int = 90, cache=None) -> tuple[list[dict], str]:
    """Daily price/market-cap/volume history for one coin.

    The free endpoint returns hourly points for a 90-day window, so we collapse
    to one row per date (last point of each day). Returns ``([{date, price,
    market_cap, volume}], error)`` — backfills real momentum history from run #1.
    """
    params: dict[str, Any] = {"vs_currency": "usd", "days": days}
    key = os.environ.get("COINGECKO_API_KEY")
    if key:
        params["x_cg_demo_api_key"] = key
    data, err = get_json(
        f"{BASE}/coins/{coingecko_id}/market_chart",
        params=params,
        cache=cache,
        cache_source="coingecko",
        cache_key=f"chart:{coingecko_id}:{days}",
    )
    if err or not isinstance(data, dict):
        return [], err or "no data"

    def _by_date(series):
        out: dict[str, float] = {}
        for point in series or []:
            if not isinstance(point, list) or len(point) < 2:
                continue
            d = datetime.fromtimestamp(point[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            out[d] = point[1]  # last point of the day wins
        return out

    prices = _by_date(data.get("prices"))
    caps = _by_date(data.get("market_caps"))
    vols = _by_date(data.get("total_volumes"))
    rows = [
        {"date": d, "price": prices[d], "market_cap": caps.get(d), "volume": vols.get(d)}
        for d in sorted(prices)
    ]
    return rows, ""


def fetch_competitors(
    competitors: list[dict], cache=None
) -> list[CompetitorSnapshot]:
    """Fetch competitor market data in a single batched call where possible.

    ``competitors`` is the parsed competitors.yaml list. Entries without a
    ``coingecko_id`` (e.g. projects with no token) are returned with an error
    note rather than skipped, so the report can show the data gap.
    """
    ts = utcnow().isoformat()
    date = today_str()
    have_ids = [c for c in competitors if c.get("coingecko_id")]
    ids = ",".join(c["coingecko_id"] for c in have_ids)
    data: list[dict] = []
    err = ""
    if ids:
        data, err = get_json(
            f"{BASE}/coins/markets",
            params=_params(ids),
            cache=cache,
            cache_source="coingecko",
            cache_key=f"markets:{ids}",
        )
        data = data or []

    results: list[CompetitorSnapshot] = []
    for c in competitors:
        snap = CompetitorSnapshot(date=date, ts=ts, name=c.get("name", "?"), slug=c.get("slug", ""))
        cid = c.get("coingecko_id")
        # Allow a manually-entered TVS proxy from the config.
        snap.tvs = c.get("tvs_usd")
        if not cid:
            snap.error = "no coingecko_id (no liquid token / manual only)"
            results.append(snap)
            continue
        if err and not data:
            snap.error = err
            results.append(snap)
            continue
        row = _row_for(data, cid)
        if row is None:
            snap.error = f"id '{cid}' not found"
            results.append(snap)
            continue
        snap.market_cap = row.get("market_cap")
        snap.volume_24h = row.get("total_volume")
        results.append(snap)
    return results
