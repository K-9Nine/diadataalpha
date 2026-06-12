"""Valuation scenarios.

Pure functions (no I/O) so they are trivially unit-testable. Two families:

  * absolute market-cap scenarios -> implied price + personal holding value,
  * relative-to-competitor scenarios -> implied DIA market cap if it reached
    X% of a competitor's market cap.

Nothing here is advice. ``implied_price = target_market_cap / circulating``.
"""

from __future__ import annotations

from typing import Any, Optional

from dia_alpha_monitor.models import (
    MARKET_CAP_SCENARIOS,
    RELATIVE_FRACTIONS,
    USER_AVG_COST_USD,
    USER_HOLDING_DIA,
)


def implied_price(target_market_cap: float, circulating_supply: Optional[float]) -> Optional[float]:
    if not circulating_supply or circulating_supply <= 0:
        return None
    return target_market_cap / circulating_supply


def holding_value(price: Optional[float], holding: float = USER_HOLDING_DIA) -> Optional[float]:
    if price is None:
        return None
    return price * holding


def market_cap_scenarios(
    circulating_supply: Optional[float],
    current_price: Optional[float] = None,
    holding: float = USER_HOLDING_DIA,
    avg_cost: float = USER_AVG_COST_USD,
    scenarios: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Return one row per market-cap scenario.

    Each row: target_market_cap, implied_price, multiple_vs_now,
    holding_value, holding_pnl, holding_roi.
    """
    scenarios = scenarios or MARKET_CAP_SCENARIOS
    cost_basis = holding * avg_cost
    rows: list[dict[str, Any]] = []
    for mc in scenarios:
        price = implied_price(mc, circulating_supply)
        value = holding_value(price, holding)
        multiple = None
        if price is not None and current_price:
            multiple = price / current_price
        pnl = None if value is None else value - cost_basis
        roi = None if (value is None or cost_basis == 0) else (value - cost_basis) / cost_basis
        rows.append(
            {
                "target_market_cap": mc,
                "implied_price": price,
                "multiple_vs_now": multiple,
                "holding_value": value,
                "holding_pnl": pnl,
                "holding_roi": roi,
            }
        )
    return rows


def relative_scenarios(
    competitor_name: str,
    competitor_market_cap: Optional[float],
    dia_market_cap: Optional[float],
    circulating_supply: Optional[float],
    fractions: list[float] | None = None,
) -> list[dict[str, Any]]:
    """If DIA reached X% of ``competitor`` market cap, what is implied?"""
    fractions = fractions or RELATIVE_FRACTIONS
    rows: list[dict[str, Any]] = []
    if not competitor_market_cap:
        return rows
    for frac in fractions:
        target_mc = competitor_market_cap * frac
        price = implied_price(target_mc, circulating_supply)
        upside = None
        if dia_market_cap and dia_market_cap > 0:
            upside = target_mc / dia_market_cap
        rows.append(
            {
                "competitor": competitor_name,
                "fraction": frac,
                "target_market_cap": target_mc,
                "implied_price": price,
                "upside_vs_now": upside,
            }
        )
    return rows


def relative_discount(
    dia_market_cap: Optional[float], competitor_market_cap: Optional[float]
) -> Optional[float]:
    """DIA market cap as a fraction of a competitor's (e.g. 0.012 = 1.2%)."""
    if not dia_market_cap or not competitor_market_cap:
        return None
    return dia_market_cap / competitor_market_cap
