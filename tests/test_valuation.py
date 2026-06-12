"""Unit tests for the valuation maths (pure functions, no I/O)."""

import math

from dia_alpha_monitor import valuation
from dia_alpha_monitor.models import USER_AVG_COST_USD, USER_HOLDING_DIA


def test_implied_price_basic():
    # 100M market cap over 200M circulating -> $0.50
    assert valuation.implied_price(100_000_000, 200_000_000) == 0.5


def test_implied_price_handles_missing_supply():
    assert valuation.implied_price(100_000_000, None) is None
    assert valuation.implied_price(100_000_000, 0) is None


def test_holding_value():
    assert valuation.holding_value(0.5, 500_000) == 250_000
    assert valuation.holding_value(None) is None


def test_market_cap_scenarios_shape_and_values():
    circ = 200_000_000
    rows = valuation.market_cap_scenarios(circ, current_price=0.20)
    # default 5 scenarios
    assert len(rows) == 5
    first = rows[0]  # 50M
    assert math.isclose(first["implied_price"], 50_000_000 / circ)
    assert math.isclose(first["holding_value"], (50_000_000 / circ) * USER_HOLDING_DIA)
    # multiple vs current price 0.20
    assert math.isclose(first["multiple_vs_now"], (50_000_000 / circ) / 0.20)


def test_market_cap_scenario_pnl_and_roi():
    circ = 100_000_000
    rows = valuation.market_cap_scenarios(circ, current_price=0.20)
    cost_basis = USER_HOLDING_DIA * USER_AVG_COST_USD  # 90,000
    # 100M scenario -> implied price 1.0 -> holding value 500,000
    row = next(r for r in rows if r["target_market_cap"] == 100_000_000)
    assert math.isclose(row["holding_value"], 500_000)
    assert math.isclose(row["holding_pnl"], 500_000 - cost_basis)
    assert math.isclose(row["holding_roi"], (500_000 - cost_basis) / cost_basis)


def test_relative_scenarios():
    rows = valuation.relative_scenarios(
        "Chainlink", competitor_market_cap=10_000_000_000,
        dia_market_cap=100_000_000, circulating_supply=200_000_000,
    )
    assert len(rows) == 4  # 1, 2.5, 5, 10%
    one_pct = rows[0]
    assert math.isclose(one_pct["target_market_cap"], 100_000_000)  # 1% of 10B
    assert math.isclose(one_pct["implied_price"], 100_000_000 / 200_000_000)
    assert math.isclose(one_pct["upside_vs_now"], 1.0)  # equals current dia mcap


def test_relative_scenarios_no_competitor_data():
    assert valuation.relative_scenarios("X", None, 100, 100) == []


def test_relative_discount():
    assert math.isclose(valuation.relative_discount(100_000_000, 10_000_000_000), 0.01)
    assert valuation.relative_discount(None, 10) is None
    assert valuation.relative_discount(10, None) is None
