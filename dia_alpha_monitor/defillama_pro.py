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
from typing import Any

from dia_alpha_monitor.http_client import get_json
# The oracle-chart parser is shared with the free /oracles path; keep one copy.
from dia_alpha_monitor.defillama import _extract_oracle_series, _to_date  # noqa: F401

PRO_BASE = "https://pro-api.llama.fi"


def _key() -> str:
    return os.environ.get("DEFILLAMA_API_KEY", "").strip()


def have_key() -> bool:
    return bool(_key())


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
