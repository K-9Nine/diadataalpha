"""Week-over-week movement alerts.

Compares each tracked metric's latest value against the snapshot closest to 7
days ago and flags any move larger than ``threshold`` percent. Rendered as an
``[ALERT]`` banner at the very top of the report so big swings can't be missed.

Guarded by history: a metric is only checked once its table spans at least
``min_history_days`` days, so a fresh DB never emits misleading day-1 alerts.
"""

from __future__ import annotations

from typing import Any, Optional

from dia_alpha_monitor.db import Database

# (label, table, column, format-hint)
_METRICS = [
    ("DIA price", "market_snapshots", "price", "price"),
    ("DIA-linked TVL proxy", "tvl_proxy", "gross_tvl", "money"),
    ("DIA self-price (API)", "dia_oracle_snapshots", "dia_price", "price"),
    ("Quoted assets (coverage)", "dia_oracle_snapshots", "quoted_assets", "int"),
    ("Total feeds", "feed_activity_snapshots", "total_feeds", "int"),
    ("Active exchange sources", "feed_activity_snapshots", "active_sources", "int"),
    ("DIA staked", "staking_snapshots", "total_staked", "int"),
]


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / old * 100.0


def week_over_week_alerts(
    db: Database, threshold: float = 10.0, min_history_days: int = 7
) -> list[dict[str, Any]]:
    """Return alerts for metrics that moved more than ``threshold`` % WoW."""
    alerts: list[dict[str, Any]] = []
    for label, table, col, fmt in _METRICS:
        try:
            if db.history_span_days(table) < min_history_days:
                continue
            latest = db.latest(table)
            if latest is None:
                continue
            new = _to_float(latest[col])
            old = db.nearest_before(table, 7, col)
            pct = _pct(new, old)
            if pct is None or abs(pct) < threshold:
                continue
            alerts.append(
                {
                    "metric": label,
                    "old": old,
                    "new": new,
                    "pct": pct,
                    "direction": "up" if pct > 0 else "down",
                    "fmt": fmt,
                }
            )
        except Exception:
            # An alert check must never break the report.
            continue
    return alerts
