"""Load and lightly validate the YAML config files.

All manual, human-editable inputs live in ``config/*.yaml``. This module
loads them defensively (a missing or malformed file yields an empty list and
a warning rather than a crash) and derives the grants / RWA / staking
adoption metrics used by the report and scorer.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml

CONFIG_DIR = os.environ.get("DIA_CONFIG_DIR", "config")


def _path(name: str) -> str:
    return os.path.join(CONFIG_DIR, name)


def _load_yaml(name: str) -> tuple[Any, str]:
    """Return (data, warning). Never raises."""
    path = _path(name)
    if not os.path.exists(path):
        return None, f"missing config file: {path}"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh), ""
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"could not parse {path}: {exc}"


def load_protocols() -> tuple[list[dict], str]:
    data, warn = _load_yaml("protocols.yaml")
    items = (data or {}).get("protocols", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_competitors() -> tuple[list[dict], str]:
    data, warn = _load_yaml("competitors.yaml")
    items = (data or {}).get("competitors", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_grants() -> tuple[list[dict], str]:
    data, warn = _load_yaml("grants.yaml")
    items = (data or {}).get("grants", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_news() -> tuple[list[dict], str]:
    data, warn = _load_yaml("news.yaml")
    items = (data or {}).get("news", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_staking() -> tuple[list[dict], str]:
    data, warn = _load_yaml("staking_snapshots.yaml")
    items = (data or {}).get("snapshots", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_oracles() -> tuple[list[dict], str]:
    data, warn = _load_yaml("oracles.yaml")
    items = (data or {}).get("chains", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_feeds_meta() -> tuple[dict, str]:
    """Manually-sourced feed figures (e.g. DIA's published RWA asset count)."""
    data, warn = _load_yaml("feeds.yaml")
    return (data if isinstance(data, dict) else {}), warn


def load_news_feeds() -> tuple[list[dict], str]:
    """RSS/Atom feeds to auto-ingest into the news tracker."""
    data, warn = _load_yaml("news_feeds.yaml")
    items = (data or {}).get("feeds", []) if isinstance(data, dict) else (data or [])
    return list(items or []), warn


def load_oracle_tvs() -> tuple[dict, str]:
    """Official DIA oracle TVS (DefiLlama), recorded manually (API is paywalled)."""
    data, warn = _load_yaml("oracle_tvs.yaml")
    return (data if isinstance(data, dict) else {}), warn


# -- derived metrics -------------------------------------------------------

def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def grants_metrics(grants: list[dict]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    chains = {g.get("chain") for g in grants if g.get("chain")}
    mainnet = [g for g in grants if str(g.get("status", "")).lower() == "mainnet"]
    rwa = [g for g in grants if g.get("RWA") in (True, "true", "True")]
    recent = []
    for g in grants:
        d = _parse_date(g.get("date_added"))
        if d and d >= cutoff:
            recent.append(g)
    return {
        "total": len(grants),
        "mainnet": len(mainnet),
        "rwa": len(rwa),
        "chains": sorted(c for c in chains if c),
        "n_chains": len(chains),
        "new_30d": len(recent),
        "new_30d_items": recent,
    }


def news_metrics(news: list[dict], top: int = 10) -> dict[str, Any]:
    rwa_items = [n for n in news if str(n.get("category", "")).lower() == "rwa"]

    def sort_key(n: dict):
        d = _parse_date(n.get("date")) or datetime.min.replace(tzinfo=timezone.utc)
        return (int(n.get("impact_score", 0) or 0), d)

    ranked = sorted(news, key=sort_key, reverse=True)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    recent_rwa = [
        n for n in rwa_items
        if (_parse_date(n.get("date")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    ]
    return {
        "total": len(news),
        "rwa_total": len(rwa_items),
        "rwa_recent_30d": len(recent_rwa),
        "top_high_impact": ranked[:top],
    }


def staking_metrics(snaps: list[dict]) -> dict[str, Any]:
    """Sort manual staking snapshots by date and compute deltas."""
    parsed = []
    for s in snaps:
        d = _parse_date(s.get("date"))
        parsed.append((d or datetime.min.replace(tzinfo=timezone.utc), s))
    parsed.sort(key=lambda t: t[0])
    ordered = [s for _, s in parsed]
    latest = ordered[-1] if ordered else None
    prev = ordered[-2] if len(ordered) >= 2 else None

    def delta(field: str):
        if latest is None or prev is None:
            return None
        a, b = latest.get(field), prev.get(field)
        if a is None or b is None:
            return None
        try:
            return float(a) - float(b)
        except (TypeError, ValueError):
            return None

    return {
        "latest": latest,
        "previous": prev,
        "n": len(ordered),
        "delta_staked": delta("total_dia_staked"),
        "delta_feeders": delta("feeders"),
        "delta_apy": delta("apy"),
        "delta_tx": delta("lasernet_tx_count"),
    }
