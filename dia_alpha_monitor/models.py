"""Lightweight data models and shared constants.

We keep these as plain dataclasses rather than an ORM to stay simple and
readable. The SQLite layer (``db.py``) handles persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


# DIA's token id on CoinGecko. Kept here so it is easy to find/change.
DIA_COINGECKO_ID = "dia-data"

# Personal-holding assumptions used in the valuation section. These are the
# user's stated position and are clearly research inputs, not advice.
USER_HOLDING_DIA = 500_000
USER_AVG_COST_USD = 0.18

# Market-cap scenarios (USD) used for implied-price valuation.
MARKET_CAP_SCENARIOS = [50_000_000, 100_000_000, 250_000_000, 500_000_000, 1_000_000_000]

# Fractions of a competitor's market cap used for relative scenarios.
RELATIVE_FRACTIONS = [0.01, 0.025, 0.05, 0.10]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today_str() -> str:
    return utcnow().strftime("%Y-%m-%d")


@dataclass
class MarketSnapshot:
    date: str
    ts: str
    price: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    fdv: Optional[float] = None
    change_1d: Optional[float] = None
    change_7d: Optional[float] = None
    change_30d: Optional[float] = None
    source: str = "coingecko"
    stale: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TvlSnapshot:
    date: str
    ts: str
    slug: str
    name: str
    tvl: Optional[float] = None
    chain_tvls_json: str = "{}"
    dia_role: str = "unknown"
    confidence: str = "low"
    source: str = "defillama"
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompetitorSnapshot:
    date: str
    ts: str
    name: str
    slug: str
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    tvs: Optional[float] = None
    source: str = "coingecko"
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreSnapshot:
    date: str
    ts: str
    total: float
    breakdown_json: str
    notes_json: str = "[]"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
