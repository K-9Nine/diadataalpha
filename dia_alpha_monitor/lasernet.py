"""Lasernet throughput collector — DIA's oracle rollup, via its public explorer.

DIA's actual oracle activity happens on **Lasernet** (its Arbitrum-Orbit oracle
rollup), not on the quiet legacy consumer-chain push-oracles. Lasernet exposes a
public Blockscout instance at ``explorer.diadata.org`` with a free, keyless REST
API. Because Lasernet is a purpose-built oracle rollup, its transaction
throughput is essentially all oracle operations — i.e. a direct, trustless
*usage* signal (the real thing the DIA-linked TVL proxy only approximates).

Snapshotting ``transactions_today`` / ``total_transactions`` daily turns oracle
throughput growth into a tracked signal, and finally gives a real source for the
``lasernet_tx_count`` that the manual staking log could never populate.
"""

from __future__ import annotations

from typing import Optional

from dia_alpha_monitor.http_client import get_json
from dia_alpha_monitor.models import LasernetSnapshot, today_str, utcnow

STATS_URL = "https://explorer.diadata.org/api/v2/stats"
CHART_URL = "https://explorer.diadata.org/api/v2/stats/charts/transactions"


def _to_int(v: object) -> Optional[int]:
    """Blockscout returns big numbers as strings; coerce defensively."""
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def fetch_lasernet(cache=None) -> LasernetSnapshot:
    """Snapshot Lasernet throughput from the Blockscout stats endpoint."""
    snap = LasernetSnapshot(date=today_str(), ts=utcnow().isoformat())
    data, err = get_json(
        STATS_URL, cache=cache, cache_source="lasernet", cache_key="stats"
    )
    if err or not isinstance(data, dict):
        snap.error = err or "no data"
        return snap
    snap.total_transactions = _to_int(data.get("total_transactions"))
    snap.transactions_today = _to_int(data.get("transactions_today"))
    snap.total_blocks = _to_int(data.get("total_blocks"))
    snap.total_addresses = _to_int(data.get("total_addresses"))
    if snap.total_transactions is None and snap.transactions_today is None:
        snap.error = "stats payload missing expected fields"
    return snap


def fetch_lasernet_history(cache=None) -> tuple[list[dict], str]:
    """Daily Lasernet transaction counts (the Blockscout tx chart, ~31 days).

    Backfilling this gives a real throughput *trend* immediately, instead of
    waiting for our own daily snapshots to accumulate. Returns
    ``([{date, transactions_count}], error)``.
    """
    data, err = get_json(CHART_URL, cache=cache, cache_source="lasernet", cache_key="tx_chart")
    if err or not isinstance(data, dict):
        return [], err or "no data"
    chart = data.get("chart") or data.get("chart_data") or []
    out: list[dict] = []
    for p in chart:
        d = p.get("date")
        c = p.get("transactions_count", p.get("tx_count", p.get("value")))
        n = _to_int(c)
        if d and n is not None:
            out.append({"date": str(d)[:10], "transactions_count": n})
    return out, ""
