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

# DIA token contract on Ethereum — the canonical address DIA's own API prices.
# Used to query api.diadata.org (DIA pricing its own token, signed).
DIA_TOKEN_ETHEREUM = "0x84cA8bc7997272c7CfB4D0Cd3D55cd942B3c9419"

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
class DiaOracleSnapshot:
    """A reading from DIA's own API (api.diadata.org) — the most trusted source.

    Holds DIA's self-reported (signed) price for the DIA token plus coverage
    stats (how many assets DIA quotes, how many exchange sources it scrapes).
    All numeric fields are Optional so a partial fetch is never fatal.
    """

    date: str
    ts: str
    dia_price: Optional[float] = None
    dia_price_yesterday: Optional[float] = None
    volume_yesterday_usd: Optional[float] = None
    quoted_assets: Optional[int] = None
    exchange_sources: Optional[int] = None
    active_scrapers: Optional[int] = None
    signature: str = ""
    source: str = "diadata.org"
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
