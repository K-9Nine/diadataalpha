"""Transparent 0-100 alpha score.

Design goals:
  * Every category is a small pure function returning points, the max for
    that category, a human-readable rationale, and a ``gap`` flag.
  * When a category's primary input is missing we award a *neutral baseline*
    (``NEUTRAL_FRACTION`` of the category max) and flag the gap, rather than
    scoring it 0. This keeps the headline number from being dominated by
    empty manual config files, while still surfacing the gap honestly.
  * No hidden magic: weights live in ``CATEGORY_MAX`` and the thresholds are
    visible inline.

The score is a research signal, not advice.
"""

from __future__ import annotations

from typing import Any, Optional

CATEGORY_MAX = {
    "momentum": 15,
    "tvl_growth": 25,
    "grants": 15,
    "rwa": 15,
    "staking": 15,
    "valuation_discount": 15,
}
TOTAL_MAX = sum(CATEGORY_MAX.values())  # 100

NEUTRAL_FRACTION = 0.4


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _neutral(category: str, reason: str) -> dict[str, Any]:
    mx = CATEGORY_MAX[category]
    return {
        "category": category,
        "points": round(mx * NEUTRAL_FRACTION, 2),
        "max": mx,
        "rationale": f"neutral baseline ({int(NEUTRAL_FRACTION*100)}% of {mx}) - {reason}",
        "gap": True,
    }


def _insufficient(category: str, reason: str) -> dict[str, Any]:
    """A trend category that lacks enough history to be scored honestly.

    Awards the neutral baseline (so the total isn't tanked) but is flagged
    distinctly so the report can show ``INSUFFICIENT DATA`` instead of a
    misleading trend number.
    """
    mx = CATEGORY_MAX[category]
    return {
        "category": category,
        "points": round(mx * NEUTRAL_FRACTION, 2),
        "max": mx,
        "rationale": f"INSUFFICIENT DATA - {reason}",
        "gap": True,
        "insufficient": True,
    }


def _result(category: str, points: float, rationale: str, gap: bool = False) -> dict[str, Any]:
    mx = CATEGORY_MAX[category]
    return {
        "category": category,
        "points": round(_clamp(points, 0, mx), 2),
        "max": mx,
        "rationale": rationale,
        "gap": gap,
    }


def score_momentum(
    change_7d: Optional[float], change_30d: Optional[float], vol_mcap_ratio: Optional[float]
) -> dict[str, Any]:
    if change_7d is None and change_30d is None:
        return _neutral("momentum", "no price-change data")
    pts = 0.0
    parts = []
    # 7d trend up to 6 points: +20% -> full, -20% -> zero, linear.
    if change_7d is not None:
        c = _clamp((change_7d + 20) / 40, 0, 1)
        pts += c * 6
        parts.append(f"7d {change_7d:+.1f}%")
    # 30d trend up to 6 points.
    if change_30d is not None:
        c = _clamp((change_30d + 30) / 60, 0, 1)
        pts += c * 6
        parts.append(f"30d {change_30d:+.1f}%")
    # Liquidity/turnover up to 3 points: 10% vol/mcap -> full.
    if vol_mcap_ratio is not None:
        pts += _clamp(vol_mcap_ratio / 0.10, 0, 1) * 3
        parts.append(f"vol/mcap {vol_mcap_ratio:.3f}")
    return _result("momentum", pts, "; ".join(parts))


MIN_TREND_HISTORY_DAYS = 7


def score_tvl_growth(
    weekly_change_pct: Optional[float],
    monthly_change_pct: Optional[float],
    n_resolved: int,
    history_days: Optional[float] = None,
) -> dict[str, Any]:
    # Trend metrics need real history. Until the TVL series spans at least a
    # week, refuse to score a change figure (which would otherwise read a
    # misleading ~0% off two near-adjacent snapshots).
    if history_days is not None and history_days < MIN_TREND_HISTORY_DAYS:
        if n_resolved <= 0:
            return _neutral("tvl_growth", "no DIA-linked TVL resolved")
        return _insufficient(
            "tvl_growth",
            f"need >={MIN_TREND_HISTORY_DAYS}d of TVL history, have {history_days:.0f}d",
        )
    if weekly_change_pct is None and monthly_change_pct is None:
        if n_resolved > 0:
            # We have TVL but no history yet (first run).
            return _neutral("tvl_growth", "TVL captured but no prior history for change")
        return _neutral("tvl_growth", "no DIA-linked TVL resolved")
    pts = 0.0
    parts = []
    # Weekly growth up to 12 points: +15% -> full, -15% -> zero.
    if weekly_change_pct is not None:
        pts += _clamp((weekly_change_pct + 15) / 30, 0, 1) * 12
        parts.append(f"7d {weekly_change_pct:+.1f}%")
    # Monthly growth up to 13 points: +30% -> full, -30% -> zero.
    if monthly_change_pct is not None:
        pts += _clamp((monthly_change_pct + 30) / 60, 0, 1) * 13
        parts.append(f"30d {monthly_change_pct:+.1f}%")
    return _result("tvl_growth", pts, "; ".join(parts))


def score_grants(new_30d: int, mainnet: int, total: int) -> dict[str, Any]:
    if total == 0:
        return _neutral("grants", "grants.yaml empty")
    pts = 0.0
    # New grants in last 30d up to 7 points: 4+ new -> full.
    pts += _clamp(new_30d / 4, 0, 1) * 7
    # Mainnet share up to 5 points.
    pts += _clamp(mainnet / max(total, 1), 0, 1) * 5
    # Breadth up to 3 points: 6+ total -> full.
    pts += _clamp(total / 6, 0, 1) * 3
    return _result(
        "grants",
        pts,
        f"{total} grants, {mainnet} mainnet, {new_30d} new in 30d",
    )


def score_rwa(rwa_grants: int, rwa_recent_news: int, rwa_total_news: int) -> dict[str, Any]:
    if rwa_grants == 0 and rwa_total_news == 0:
        return _neutral("rwa", "no RWA grants or news tracked")
    pts = 0.0
    # RWA grants up to 8 points: 3+ -> full.
    pts += _clamp(rwa_grants / 3, 0, 1) * 8
    # Recent RWA news momentum up to 4 points: 3+ in 30d -> full.
    pts += _clamp(rwa_recent_news / 3, 0, 1) * 4
    # Standing RWA coverage up to 3 points: 5+ items -> full.
    pts += _clamp(rwa_total_news / 5, 0, 1) * 3
    return _result(
        "rwa",
        pts,
        f"{rwa_grants} RWA grants, {rwa_recent_news} RWA news in 30d, {rwa_total_news} total",
    )


def score_staking(
    delta_staked: Optional[float],
    delta_feeders: Optional[float],
    delta_tx: Optional[float],
    has_latest: bool,
) -> dict[str, Any]:
    if not has_latest:
        return _neutral("staking", "no staking snapshot in staking_snapshots.yaml")
    if delta_staked is None and delta_feeders is None and delta_tx is None:
        return _neutral("staking", "only one staking snapshot - no change yet")
    pts = 0.0
    parts = []
    # Staked rising up to 7 points (any positive delta -> strong signal).
    if delta_staked is not None:
        pts += 7 if delta_staked > 0 else (3.5 if delta_staked == 0 else 0)
        parts.append(f"staked Δ{delta_staked:+,.0f}")
    # New feeders up to 5 points.
    if delta_feeders is not None:
        pts += _clamp(delta_feeders / 2, 0, 1) * 5 if delta_feeders > 0 else 0
        parts.append(f"feeders Δ{delta_feeders:+.0f}")
    # Lasernet tx growth up to 3 points.
    if delta_tx is not None:
        pts += 3 if delta_tx > 0 else 0
        parts.append(f"tx Δ{delta_tx:+,.0f}")
    return _result("staking", pts, "; ".join(parts) or "no change")


def score_valuation_discount(best_discount: Optional[float]) -> dict[str, Any]:
    """A deeper discount vs the leading oracle = more potential upside.

    ``best_discount`` is DIA market cap / leading competitor market cap.
    1% or less -> full marks; 10%+ -> minimal.
    """
    if best_discount is None:
        return _neutral("valuation_discount", "no competitor market-cap data")
    # 0.01 -> full 15, 0.10 -> ~0, linear on log-ish scale.
    score = _clamp((0.10 - best_discount) / (0.10 - 0.01), 0, 1) * 15
    return _result(
        "valuation_discount",
        score,
        f"DIA is {best_discount*100:.2f}% of leading oracle market cap",
    )


def aggregate(categories: list[dict[str, Any]]) -> dict[str, Any]:
    total = round(sum(c["points"] for c in categories), 2)
    gaps = [c["category"] for c in categories if c.get("gap")]
    insufficient = [c["category"] for c in categories if c.get("insufficient")]
    return {
        "total": total,
        "max": TOTAL_MAX,
        "categories": categories,
        "data_gaps": gaps,
        "insufficient": insufficient,
    }
