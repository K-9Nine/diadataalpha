"""DefiLlama **Pro** API — official DIA oracle TVS (+ history) and protocol fees.

Requires the ``DEFILLAMA_API_KEY`` env var (Pro plan). Without it every function
no-ops gracefully and the tool falls back to the manual figure in
``config/oracle_tvs.yaml``.

The Pro base is ``https://pro-api.llama.fi/{KEY}``. The ``/api/oracles`` response
shape isn't publicly documented and has varied over time, so the chart parser is
**defensive** (handles dict-keyed-by-timestamp and list-of-pairs) and the raw
payload is cached to ``raw_cache`` (via ``get_json``) so parsing can be corrected
from a real response if needed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dia_alpha_monitor.http_client import get_json

PRO_BASE = "https://pro-api.llama.fi"


def _key() -> str:
    return os.environ.get("DEFILLAMA_API_KEY", "").strip()


def have_key() -> bool:
    return bool(_key())


def _to_date(ts: Any) -> str:
    try:
        t = int(float(ts))
        if t > 1_000_000_000_000:  # milliseconds -> seconds
            t //= 1000
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(ts)[:10]


def _coerce_tvs(v: Any) -> float | None:
    """Return the TVS value for one oracle at one timestamp, or ``None``.

    The per-oracle value is either a bare number or, in the real live payload, a
    breakdown dict ``{"tvl": <num>, "staking": ..., "pool2": ..., "borrowed": ...}``
    where ``tvl`` is the secured value (TVS) we report.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        tvl = v.get("tvl")
        if isinstance(tvl, (int, float)) and not isinstance(tvl, bool):
            return float(tvl)
    return None


def _extract_oracle_series(data: dict, oracle: str) -> dict[str, float]:
    """Pull a {date: tvs} series for one oracle from an /api/oracles payload.

    Tolerant of the shapes seen in the wild:
      A)  {"chart": {"<ts>": {"DIA": tvs, ...}, ...}}
      A') {"chart": {"<ts>": {"DIA": {"tvl": tvs, ...}, ...}, ...}}  (real live shape)
      B)  {"chart": [[<ts>, {"DIA": tvs, ...}], ...]}
    The per-oracle value may be a bare number or a ``{"tvl": ...}`` breakdown dict.
    """
    chart = data.get("chart")
    series: dict[str, float] = {}
    if isinstance(chart, dict):
        for ts, mapping in chart.items():
            if isinstance(mapping, dict):
                v = _coerce_tvs(mapping.get(oracle))
                if v is not None:
                    series[_to_date(ts)] = v
    elif isinstance(chart, list):
        for point in chart:
            if isinstance(point, (list, tuple)) and len(point) == 2 and isinstance(point[1], dict):
                v = _coerce_tvs(point[1].get(oracle))
                if v is not None:
                    series[_to_date(point[0])] = v
    return series


def fetch_oracle_tvs_series(oracle: str = "DIA", cache=None) -> tuple[list[dict], str]:
    """Return ``([{date, tvs_usd}], error)`` for one oracle, newest last."""
    key = _key()
    if not key:
        return [], "no DEFILLAMA_API_KEY"
    data, err = get_json(
        f"{PRO_BASE}/{key}/api/oracles",
        cache=cache,
        cache_source="defillama_pro",
        cache_key="oracles",
    )
    if err or not isinstance(data, dict):
        return [], err or "no data"
    series = _extract_oracle_series(data, oracle)
    if not series:
        return [], f"oracle '{oracle}' not found in /api/oracles chart"
    return [{"date": d, "tvs_usd": series[d]} for d in sorted(series)], ""


def fetch_protocol_fees(slug: str, cache=None) -> tuple[dict, str]:
    """Return ``({total_24h, total_7d, total_30d, total_all_time}, error)``.

    Best-effort: many oracles aren't in DefiLlama's fees dataset (404 -> error).
    """
    key = _key()
    if not key:
        return {}, "no DEFILLAMA_API_KEY"
    data, err = get_json(
        f"{PRO_BASE}/{key}/api/summary/fees/{slug}",
        cache=cache,
        cache_source="defillama_pro",
        cache_key=f"fees:{slug}",
    )
    if err or not isinstance(data, dict):
        return {}, err or "no data"
    return {
        "total_24h": data.get("total24h"),
        "total_7d": data.get("total7d"),
        "total_30d": data.get("total30d"),
        "total_all_time": data.get("totalAllTime"),
    }, ""
