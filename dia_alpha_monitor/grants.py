"""Grant funnel analysis.

Turns the flat ``config/grants.yaml`` adoption list into a funnel:

    announced  ->  testnet  ->  mainnet        (inactive = churned)

and computes conversion rates plus a list of *stale* grants — ones still stuck
pre-mainnet after more than ``stale_days`` (default 90). A grant that was
announced months ago and never reached mainnet is a soft bear signal (adoption
that didn't convert), so surfacing it matters.

Pure functions only — fully unit-testable, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# Status order, earliest funnel stage first. "inactive" is terminal/churned.
FUNNEL_STAGES = ("announced", "testnet", "mainnet")
PRE_MAINNET = ("announced", "testnet")


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def grant_funnel(
    grants: list[dict], stale_days: int = 90, now: Optional[datetime] = None
) -> dict[str, Any]:
    """Build funnel counts, conversion rates and a stale-grant list."""
    now = now or datetime.now(timezone.utc)
    counts = {"announced": 0, "testnet": 0, "mainnet": 0, "inactive": 0}
    for g in grants:
        status = str(g.get("status", "")).strip().lower()
        if status in counts:
            counts[status] += 1

    total = len(grants)
    mainnet = counts["mainnet"]
    reached_testnet = counts["testnet"] + counts["mainnet"]

    def rate(num: int) -> Optional[float]:
        return round(num / total, 4) if total else None

    stale: list[dict] = []
    for g in grants:
        status = str(g.get("status", "")).strip().lower()
        if status not in PRE_MAINNET:
            continue
        d = _parse_date(g.get("date_added"))
        if d is None:
            continue
        age = (now - d).days
        if age > stale_days:
            stale.append(
                {
                    "project": g.get("project", "?"),
                    "chain": g.get("chain", "?"),
                    "status": status,
                    "days": age,
                    "date_added": str(g.get("date_added", "")),
                }
            )
    stale.sort(key=lambda s: s["days"], reverse=True)

    return {
        "total": total,
        "counts": counts,
        "reached_testnet": reached_testnet,
        # Share of all grants that got at least to testnet, and that went live.
        "to_testnet_rate": rate(reached_testnet),
        "to_mainnet_rate": rate(mainnet),
        "stale_days": stale_days,
        "stale": stale,
        "n_stale": len(stale),
    }
