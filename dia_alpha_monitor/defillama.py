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


def fetch_protocol_tvl(protocol: dict, cache=None) -> TvlSnapshot:
    """Fetch one protocol's TVL. ``protocol`` is an entry from protocols.yaml."""
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
