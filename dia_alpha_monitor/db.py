"""SQLite persistence layer.

One small wrapper class owns the connection and the schema. We store:
  * ``raw_cache``        - raw API responses (audit / offline inspection),
  * ``market_snapshots`` - daily DIA market data,
  * ``tvl_snapshots``    - per-protocol DeFiLlama TVL,
  * ``tvl_proxy``        - aggregated DIA-linked TVL proxy,
  * ``competitor_snapshots`` - competitor market data,
  * ``staking_snapshots``    - ingested manual staking entries,
  * ``score_snapshots``      - alpha-score history,
  * ``dia_oracle_snapshots`` - DIA's own API readings (self-price + coverage).

Snapshots are append-only so we can compute change-over-time.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional

from dia_alpha_monitor.models import utcnow

DEFAULT_DB_PATH = os.environ.get("DIA_DB_PATH", "dia_alpha_monitor.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    price REAL, market_cap REAL, volume_24h REAL,
    circulating_supply REAL, total_supply REAL, fdv REAL,
    change_1d REAL, change_7d REAL, change_30d REAL,
    source TEXT, stale INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tvl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    slug TEXT, name TEXT, tvl REAL,
    chain_tvls_json TEXT, dia_role TEXT, confidence TEXT,
    source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS tvl_proxy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    gross_tvl REAL, confidence_weighted_tvl REAL,
    n_protocols INTEGER, n_resolved INTEGER
);

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    name TEXT, slug TEXT,
    market_cap REAL, volume_24h REAL, tvs REAL,
    source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS staking_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    total_staked REAL, feeders INTEGER, apy REAL,
    lasernet_tx_count REAL, source TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    total REAL, breakdown_json TEXT, notes_json TEXT
);

CREATE TABLE IF NOT EXISTS dia_oracle_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    dia_price REAL, dia_price_yesterday REAL, volume_yesterday_usd REAL,
    quoted_assets INTEGER, exchange_sources INTEGER, active_scrapers INTEGER,
    signature TEXT, source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS feed_activity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    total_feeds INTEGER, rwa_feeds INTEGER, crypto_feeds INTEGER,
    n_blockchains INTEGER, active_sources INTEGER,
    source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS oracle_activity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    chain TEXT, oracle_address TEXT, rpc_url TEXT,
    update_count INTEGER, latest_block INTEGER,
    from_block INTEGER, to_block INTEGER,
    source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS lasernet_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ts TEXT NOT NULL,
    total_transactions INTEGER, transactions_today INTEGER,
    total_blocks INTEGER, total_addresses INTEGER,
    source TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS ingested_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_seen TEXT NOT NULL,
    date TEXT,
    title TEXT, url TEXT UNIQUE,
    source TEXT, category TEXT, impact_score INTEGER
);
"""


class Database:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- caching -----------------------------------------------------------
    def cache_raw(self, source: str, cache_key: str, status: str, payload: str) -> None:
        self.conn.execute(
            "INSERT INTO raw_cache(source, cache_key, fetched_at, status, payload)"
            " VALUES (?,?,?,?,?)",
            (source, cache_key, utcnow().isoformat(), status, payload),
        )
        self.conn.commit()

    # -- generic insert helpers -------------------------------------------
    def insert(self, table: str, row: dict[str, Any]) -> int:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        cur = self.conn.execute(
            f"INSERT INTO {table}({cols}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def latest(self, table: str, where: str = "", params: tuple = ()) -> Optional[sqlite3.Row]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY id DESC LIMIT 1"
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def previous(self, table: str, where: str = "", params: tuple = ()) -> Optional[sqlite3.Row]:
        """The row immediately before the latest one (for change calcs)."""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY id DESC LIMIT 1 OFFSET 1"
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def rows_since(self, table: str, days: int) -> list[sqlite3.Row]:
        """All rows whose date is within ``days`` of now (string compare on date)."""
        from datetime import timedelta

        cutoff = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        cur = self.conn.execute(
            f"SELECT * FROM {table} WHERE date >= ? ORDER BY id ASC", (cutoff,)
        )
        return cur.fetchall()

    def all_rows(self, table: str) -> list[sqlite3.Row]:
        cur = self.conn.execute(f"SELECT * FROM {table} ORDER BY id ASC")
        return cur.fetchall()

    def history_span_days(self, table: str, where: str = "", params: tuple = ()) -> float:
        """Days between the earliest and latest ``date`` in a snapshot table.

        Used to gate trend metrics that are only meaningful with enough history
        (e.g. require >= 7 days before scoring weekly TVL change). Returns 0.0
        when the table has zero or one distinct date.
        """
        from datetime import date as _date

        sql = f"SELECT MIN(date) AS mn, MAX(date) AS mx FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.conn.execute(sql, params).fetchone()
        if not row or not row["mn"] or not row["mx"]:
            return 0.0
        try:
            mn = _date.fromisoformat(str(row["mn"])[:10])
            mx = _date.fromisoformat(str(row["mx"])[:10])
        except ValueError:
            return 0.0
        return float((mx - mn).days)

    def nearest_before(
        self, table: str, days_ago: int, value_col: str, where: str = "", params: tuple = ()
    ) -> Optional[float]:
        """Return ``value_col`` from the snapshot closest to ``days_ago`` days back.

        Used to compute weekly / 30-day change without assuming daily cadence.
        """
        from datetime import timedelta

        target = (utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        sql = f"SELECT {value_col} AS v, date FROM {table}"
        clauses = [f"{value_col} IS NOT NULL"]
        if where:
            clauses.append(where)
        sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ABS(julianday(date) - julianday(?)) ASC LIMIT 1"
        cur = self.conn.execute(sql, (*params, target))
        row = cur.fetchone()
        return None if row is None or row["v"] is None else float(row["v"])
