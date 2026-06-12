# dia-alpha-monitor

A **local** investor-research tool that helps you detect early "alpha" signals
for **DIA Data / DIA Oracles** before the wider market prices them in.

The core investment question it is built around: *is DIA evolving from a
governance token into usage-based oracle infrastructure?* DIA describes the DIA
token as native gas on **Lasernet**, used for **staking** to secure oracle
operations and for **governance**, and runs **Oracle Grants** across 20+ chains
plus **RWA** feeds (equities, ETFs, commodities, FX, bonds, inflation,
proof-of-reserves, NAV/fair-value, custom). The unresolved question is whether
those integrations become **real usage, TVS and fees**. This tool tracks proxies
for that.

> **Not financial advice.** Every output is a *research signal*. Several
> inputs are **proxies** or **manual** entries and are labelled as such. In
> particular the "DIA-linked TVL proxy" is **NOT** official DIA TVS - see below.

---

## What it does

- **Market data** (CoinGecko, free): DIA price, market cap, volume, supply, FDV,
  1d/7d/30d change, volume/market-cap ratio. Daily snapshots in SQLite.
- **DIA-linked TVL proxy** (DeFiLlama, free): TVL of a configurable watchlist of
  protocols believed to use DIA oracles, with manual `dia_role` / `confidence` /
  `evidence_url`. Produces a gross proxy and a **confidence-weighted** proxy,
  plus weekly and 30-day change.
- **Grants & adoption tracker** (manual YAML): totals, mainnet count, RWA count,
  chains represented, new grants in the last 30 days.
- **RWA narrative tracker** (manual YAML): the 10 most recent high-impact items.
- **Staking / Lasernet tracker** (manual YAML): total staked, Feeders, APY,
  Lasernet tx count, with change flags.
- **Competitor monitor** (CoinGecko): Chainlink, Pyth, RedStone, API3, Chronicle
  market caps / volume; DIA relative discount; valuation scenarios.
- **Transparent alpha score (0-100)** with a visible per-category breakdown,
  bullish/bearish changes since the last run, and data-gap flags.
- **Investor report** in the terminal (rich) and an optional **Streamlit**
  dashboard.

---

## Install

Requires **Python 3.11+**. Use `uv` (recommended) or `poetry`/`pip`.

### Using uv

```bash
uv venv
source .venv/bin/activate
uv pip install -e .            # core
uv pip install -e '.[dashboard,dev]'   # + Streamlit + pytest
```

### Using pip / venv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dashboard,dev]'
```

### Using poetry

```bash
poetry install
poetry run python -m dia_alpha_monitor run
```

Copy the env template (all values optional - it runs with zero config):

```bash
cp .env.example .env
```

---

## Run

```bash
# 1. Collect data and store snapshots
python -m dia_alpha_monitor run

# 2. Print the concise investor report
python -m dia_alpha_monitor report

# 3. Export all tables to CSV in ./exports
python -m dia_alpha_monitor export

# Optional dashboard
streamlit run dashboard.py
```

Run `run` regularly (e.g. daily). Change-over-time metrics and the
bullish/bearish diff need **at least two runs** of history.

If a data source is down or a slug/id is wrong, the run **does not stop** - the
failure is recorded (in the report and the `raw_cache` table) and everything
else continues.

---

## Edit the configs

All manual inputs live in `config/*.yaml`. They ship with **clearly-labelled
EXAMPLE placeholders** so the report renders out of the box - replace them with
verified entries.

| File | Purpose | Key fields |
|------|---------|-----------|
| `protocols.yaml` | DeFiLlama watchlist for the TVL proxy | `slug`, `dia_role`, `confidence`, `evidence_url` |
| `competitors.yaml` | Competitor oracles | `coingecko_id`, optional `tvs_usd` |
| `grants.yaml` | Oracle Grants / adoption | `chain`, `status`, `product`, `RWA`, `evidence_url` |
| `news.yaml` | RWA / narrative items | `category`, `impact_score` (1-5), `url` |
| `staking_snapshots.yaml` | Manual staking/Lasernet log | `total_dia_staked`, `feeders`, `apy`, `lasernet_tx_count` |

**To verify a protocol's TVL slug:** open `https://defillama.com/protocol/<slug>`.
A wrong slug shows as an error on that row in the report; fix it in the YAML.

**To find a CoinGecko id:** use `https://api.coingecko.com/api/v3/coins/list`
and match by symbol/name, then set `coingecko_id` in `competitors.yaml`.

---

## Export CSV

```bash
python -m dia_alpha_monitor export            # -> ./exports/*.csv
python -m dia_alpha_monitor export --out /tmp # custom directory
```

One CSV per table: `market_snapshots`, `tvl_snapshots`, `tvl_proxy`,
`competitor_snapshots`, `staking_snapshots`, `score_snapshots`.

---

## Interpreting the alpha score

A transparent **0-100** score. Weights (also printed in the report):

| Category | Max | What it rewards |
|----------|-----|-----------------|
| Price/volume momentum | 15 | 7d/30d price trend + turnover (vol/mcap) |
| **TVL/TVS proxy growth** | **25** | weekly + 30d growth of the DIA-linked TVL proxy |
| Grants/adoption growth | 15 | total + mainnet share + new grants (30d) |
| RWA-specific traction | 15 | RWA grants + recent RWA news momentum |
| Staking/Lasernet growth | 15 | staked supply, Feeders, Lasernet tx deltas |
| Relative valuation discount | 15 | deeper discount vs the leading oracle = more potential upside |

**Missing data is not scored as zero.** When a category's primary input is
absent, it gets a **neutral baseline (40% of its max)** and is flagged as a
*data gap*, so the headline number isn't dominated by empty manual files. Treat
the score as a *direction-of-travel* signal and always read the per-category
breakdown and the data-gap list, not just the total.

The report also shows **bullish** and **bearish** category changes since the
previous run, and a **"What would change my mind?"** section framing the bull /
bear thesis-breakers.

### Valuation scenarios

Implied price = `target_market_cap / circulating_supply`. The report shows
$50m / $100m / $250m / $500m / $1bn scenarios with implied price, multiple vs
now, and **your personal position** (assumed **500,000 DIA @ ~$0.18** avg cost,
staked on Lasernet - edit in `dia_alpha_monitor/models.py`). It also shows
relative scenarios if DIA reaches 1% / 2.5% / 5% / 10% of Chainlink / Pyth /
RedStone market cap.

---

## Limitations (read this)

- **The "DIA-linked TVL proxy" is NOT official DIA TVS.** It is the TVL of
  protocols *we put on a watchlist*. Until you verify each `dia_role` /
  `confidence` against real evidence, treat it as a hypothesis, not a fact.
- **Manual files can be stale or wrong.** Grants, news and staking are
  hand-entered; the shipped rows are placeholders.
- **CoinGecko / DeFiLlama free endpoints** can rate-limit or change ids/slugs.
  Failures are recorded, not fatal. Stale market data is flagged `(STALE)`.
- **No paid APIs** are used in v1. No on-chain indexing of actual DIA oracle
  reads/fees yet - that's the obvious v2.
- This is a **research aid, not advice.** Do your own verification.

---

## Project layout

```
dia-alpha-monitor/
  pyproject.toml
  README.md
  .env.example
  config/            # manual, human-editable YAML inputs
    protocols.yaml  grants.yaml  news.yaml  staking_snapshots.yaml  competitors.yaml
  dia_alpha_monitor/
    __init__.py  __main__.py  cli.py  db.py  http_client.py
    coingecko.py  defillama.py  config_loader.py
    scoring.py  reporting.py  valuation.py  models.py
  dashboard.py       # optional Streamlit app
  exports/           # CSV output
  tests/             # pytest (valuation + scoring + pipeline)
```

## Tests

```bash
python -m pytest
```

Covers the valuation maths, the scoring model, config loading, the TVL-proxy
aggregation, graceful handling of missing configs, and the CSV export command.
No network access is required to run the tests.
