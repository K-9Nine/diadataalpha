"""DeFiLlama collector (free public API).

We pull per-protocol TVL via ``/protocol/{slug}`` which includes a
``currentChainTvls`` breakdown. Slugs are best-effort guesses maintained in
``config/protocols.yaml``; a wrong slug fails gracefully and is recorded as
an error on that protocol's snapshot so the report can flag it.

IMPORTANT: the aggregate produced here is a *DIA-linked TVL proxy*. It is the
TVL of protocols we believe use (or may use) DIA oracles. It is NOT official
DIA TVS and must always be labelled as a proxy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from dia_alpha_monitor.http_client import get_json
from dia_alpha_monitor.models import TvlSnapshot, today_str, utcnow

BASE = "https://api.llama.fi"

# Confidence weights used to build the confidence-weighted proxy.
CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.2}


def _extract_chain_tvls(payload: dict) -> dict[str, float]:
    """Pull a {chain: tvl} mapping from a /protocol response."""
    raw = payload.get("currentChainTvls") or {}
    out: dict[str, float] = {}
    for chain, val in raw.items():
        # DeFiLlama suffixes like "-staking", "-borrowed" are excluded from
        # the headline TVL; keep only plain chain keys for the breakdown.
        if "-" in chain:
            continue
        if isinstance(val, (int, float)):
            out[chain] = float(val)
    return out


def _fetch_chain_tvl(slug: str, snap: TvlSnapshot, cache=None) -> TvlSnapshot:
    """Fetch chain-level TVL for an "ecosystem" entry.

    Chains are not addressable via ``/protocol/{slug}`` (that 400s). We use
    ``/v2/historicalChainTvl/{chain}`` and take the latest point. ``slug`` here
    is the DeFiLlama chain name, e.g. ``Plume Mainnet`` or ``Somnia``.
    """
    data, err = get_json(
        f"{BASE}/v2/historicalChainTvl/{slug}",
        cache=cache,
        cache_source="defillama",
        cache_key=f"chain:{slug}",
    )
    if err or not data:
        snap.error = err or "no data"
        return snap
    if isinstance(data, list) and data and isinstance(data[-1], dict):
        snap.tvl = round(float(data[-1].get("tvl", 0.0)), 2)
        snap.chain_tvls_json = json.dumps({slug: snap.tvl})
    else:
        snap.error = "unexpected chain payload"
    return snap


def fetch_protocol_tvl(protocol: dict, cache=None) -> TvlSnapshot:
    """Fetch one protocol's TVL. ``protocol`` is an entry from protocols.yaml.

    ``kind: chain`` entries are fetched via the chain TVL endpoint; everything
    else (the default ``protocol``) via ``/protocol/{slug}``.
    """
    slug = protocol.get("slug", "")
    snap = TvlSnapshot(
        date=today_str(),
        ts=utcnow().isoformat(),
        slug=slug,
        name=protocol.get("name", slug or "?"),
        dia_role=protocol.get("dia_role", "unknown"),
        confidence=protocol.get("confidence", "low"),
    )
    if not slug:
        snap.error = "no slug configured"
        return snap

    if protocol.get("kind") == "chain":
        return _fetch_chain_tvl(slug, snap, cache=cache)

    data, err = get_json(
        f"{BASE}/protocol/{slug}",
        cache=cache,
        cache_source="defillama",
        cache_key=f"protocol:{slug}",
    )
    if err or not data:
        snap.error = err or "no data"
        return snap

    chain_tvls = _extract_chain_tvls(data)
    snap.chain_tvls_json = json.dumps(chain_tvls)
    # Headline current TVL: prefer summing chain breakdown, fall back to last
    # point of the tvl history series.
    if chain_tvls:
        snap.tvl = round(sum(chain_tvls.values()), 2)
    else:
        series = data.get("tvl") or []
        if series and isinstance(series[-1], dict):
            snap.tvl = series[-1].get("totalLiquidityUSD")
    return snap


def fetch_all_protocols(protocols: list[dict], cache=None) -> list[TvlSnapshot]:
    return [fetch_protocol_tvl(p, cache=cache) for p in protocols]


# --------------------------------------------------------------------------
# Official per-oracle TVS via the FREE /oracles endpoint.
#
# DefiLlama's public oracles page (defillama.com/oracles) is rendered from
# ``https://api.llama.fi/oracles``, which is part of the free open API. This
# gives us the *official* DIA Total Value Secured (the value DIA's oracles
# actually secure) WITHOUT a paid Pro key, replacing the manually-maintained
# figure in ``config/oracle_tvs.yaml``.
#
# The chart shape isn't formally documented and has varied, so the parser is
# defensive (handles dict-keyed-by-timestamp and list-of-pairs). If the
# endpoint ever requires Pro after all, ``get_json`` returns an error and the
# caller falls back to the manual figure — so this never regresses behaviour.
# (``defillama_pro.py`` reuses these helpers for the Pro ``/api/oracles`` path.)
# --------------------------------------------------------------------------


def _to_date(ts: Any) -> str:
    try:
        t = int(float(ts))
        if t > 1_000_000_000_000:  # milliseconds -> seconds
            t //= 1000
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(ts)[:10]


def _extract_oracle_series(data: dict, oracle: str) -> dict[str, float]:
    """Pull a {date: tvs} series for one oracle from an oracles payload.

    Tolerant of the two shapes seen in the wild:
      A) {"chart": {"<ts>": {"DIA": tvs, ...}, ...}}
      B) {"chart": [[<ts>, {"DIA": tvs, ...}], ...]}
    """
    chart = data.get("chart")
    series: dict[str, float] = {}
    if isinstance(chart, dict):
        for ts, mapping in chart.items():
            if isinstance(mapping, dict):
                v = mapping.get(oracle)
                if isinstance(v, (int, float)):
                    series[_to_date(ts)] = float(v)
    elif isinstance(chart, list):
        for point in chart:
            if isinstance(point, (list, tuple)) and len(point) == 2 and isinstance(point[1], dict):
                v = point[1].get(oracle)
                if isinstance(v, (int, float)):
                    series[_to_date(point[0])] = float(v)
    return series


def fetch_oracle_tvs_series(oracle: str = "DIA", cache=None) -> tuple[list[dict], str]:
    """Official oracle TVS series via the free ``/oracles`` endpoint.

    Returns ``([{date, tvs_usd}], error)`` for one oracle, newest last. No API
    key required. On any failure (incl. an unexpected paywall) the error is
    returned and the caller falls back to the manual figure.
    """
    data, err = get_json(
        f"{BASE}/oracles",
        cache=cache,
        cache_source="defillama",
        cache_key="oracles",
    )
    if err or not isinstance(data, dict):
        return [], err or "no data"
    series = _extract_oracle_series(data, oracle)
    if not series:
        return [], f"oracle '{oracle}' not found in /oracles chart"
    return [{"date": d, "tvs_usd": series[d]} for d in sorted(series)], ""


def compute_proxy(snapshots: list[TvlSnapshot]) -> dict[str, Any]:
    """Aggregate per-protocol TVL into gross and confidence-weighted proxies."""
    gross = 0.0
    weighted = 0.0
    resolved = 0
    for s in snapshots:
        if s.tvl is None:
            continue
        resolved += 1
        gross += s.tvl
        weighted += s.tvl * CONFIDENCE_WEIGHTS.get(s.confidence, 0.2)
    return {
        "gross_tvl": round(gross, 2),
        "confidence_weighted_tvl": round(weighted, 2),
        "n_protocols": len(snapshots),
        "n_resolved": resolved,
    }
