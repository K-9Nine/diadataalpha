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

# Monetization tripwire thresholds. Lasernet gas is currently a trivial, fully
# subsidized fee surface (~$0.14/day, ~$50/yr) and is *internal network gas, not
# customer revenue* — see ANALYSIS.md §7. The bull case needs the grants->paid
# transition to turn real fee flow on; these constants define what "turning on"
# looks like on-chain so the report flags it automatically.
MATERIALITY_USD_YEAR = 100_000.0  # below this the gas-fee surface is immaterial
INFLECTION_MULTIPLE = 5.0         # gas-usage jump vs baseline that trips the wire


def _to_int(v: object) -> Optional[int]:
    """Blockscout returns big numbers as strings; coerce defensively."""
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: object) -> Optional[float]:
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return None


def estimate_daily_fee_dia(gas_used_today: Optional[int], gas_price_gwei: Optional[float]) -> Optional[float]:
    """Approximate the day's Lasernet gas fees in DIA (gas_used x gas_price).

    A coarse estimate (effective per-tx prices vary), but precise enough for a
    tripwire: the signal is the *inflection*, not the third decimal.
    """
    if gas_used_today is None or gas_price_gwei is None:
        return None
    return gas_used_today * gas_price_gwei * 1e-9  # Gwei -> DIA


def monetization_signal(
    gas_used_today: Optional[int],
    gas_price_gwei: Optional[float],
    network_utilization: Optional[float],
    dia_price: Optional[float],
    baseline_gas_used: Optional[int] = None,
) -> dict:
    """Assess the Lasernet fee surface and whether it has inflected.

    Returns the estimated daily/annualized gas fee (DIA + USD), and an
    ``inflection`` flag that trips when the annualized fee crosses the
    materiality threshold OR daily gas usage jumps >= INFLECTION_MULTIPLE x a
    trailing baseline. Until then the surface reads as dormant/subsidized.
    """
    fee_dia = estimate_daily_fee_dia(gas_used_today, gas_price_gwei)
    fee_usd_day = fee_dia * dia_price if (fee_dia is not None and dia_price) else None
    fee_usd_year = fee_usd_day * 365 if fee_usd_day is not None else None

    inflection = False
    reasons: list[str] = []
    if fee_usd_year is not None and fee_usd_year >= MATERIALITY_USD_YEAR:
        inflection = True
        reasons.append(f"annualised gas-fee ≈ ${fee_usd_year:,.0f} ≥ ${MATERIALITY_USD_YEAR:,.0f}")
    if (
        baseline_gas_used and gas_used_today
        and baseline_gas_used > 0
        and gas_used_today >= INFLECTION_MULTIPLE * baseline_gas_used
    ):
        inflection = True
        reasons.append(f"gas usage {gas_used_today / baseline_gas_used:.1f}x baseline")

    return {
        "fee_dia_day": fee_dia,
        "fee_usd_day": fee_usd_day,
        "fee_usd_year": fee_usd_year,
        "network_utilization": network_utilization,
        "gas_used_today": gas_used_today,
        "baseline_gas_used": baseline_gas_used,
        "inflection": inflection,
        "reasons": reasons,
    }


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
    snap.gas_used_today = _to_int(data.get("gas_used_today"))
    gp = data.get("gas_prices")
    if isinstance(gp, dict):
        snap.gas_price_gwei = _to_float(gp.get("average") or gp.get("fast") or gp.get("slow"))
    snap.network_utilization = _to_float(data.get("network_utilization_percentage"))
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
