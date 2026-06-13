# Handoff — dia-alpha-monitor

> Pick-up doc for a fresh Claude Code session (or a human). Read this first.

## TL;DR
- **What it is:** a local Python tool that collects DIA Data / DIA Oracles
  signals (market, DIA-linked TVL proxy, grants, RWA news, staking, competitors)
  into SQLite and prints a transparent 0–100 "alpha score" + investor report.
- **Status:** **built, tested (44 passing), committed, and pushed.** v1 + v2.
  Live APIs validated; DIA's own API (`dia_api.py`) is a primary signed source.
  v2 added: feed-coverage tracker, on-chain oracle polling, grant funnel,
  ≥7-day trend gating, a week-over-week [ALERT] banner, and a **Lasernet
  throughput** collector (real oracle-usage signal via explorer.diadata.org).
- **Branch:** PR #1 (`claude/dia-alpha-monitor-build-8p1br6`) is **merged into
  `main`**. Current work continues on `claude/friendly-hawking-2tu1jf`.
- **Repo:** `K-9Nine/diadataalpha` (this is the target repo; `answergraph3` is unrelated).

## The one open blocker — RESOLVED ✅
Live API data is now validated against the real endpoints. As of 2026-06-12 a
fresh session had full egress: CoinGecko `/ping` → 200, DeFiLlama `/protocols`
→ 200. `run` populates **8/8 TVL rows** and **4/5 competitors** (Chronicle has
no liquid token by design). If a future session loses connectivity, the symptom
is `403 Host not in allowlist`; that means the open-internet policy hasn't
applied (it only takes effect in a newly-started session).

### Quick start in a new session
```bash
cd diadataalpha
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'
python -m dia_alpha_monitor run        # hits live APIs
python -m dia_alpha_monitor report
python -m pytest                       # expect 30 passed
```

## Live validation (done 2026-06-12)
All best-guess identifiers were checked against the live APIs and corrected:

1. **DIA CoinGecko id** = `dia-data` — **confirmed correct** (price ≈ $0.124,
   mcap ≈ $14.9M). In `models.py` `DIA_COINGECKO_ID`.
2. **Competitor `coingecko_id`s** (`config/competitors.yaml`) — all resolve,
   including `redstone-oracles` (previously uncertain — **confirmed**).
   Chronicle has `coingecko_id: null` and shows as a data gap by design.
3. **DeFiLlama slugs** (`config/protocols.yaml`) — corrected:
   - `parallel` → `parallel-protocol-v3` (the live CDP stablecoin protocol).
   - `zest-protocol` → `zest-v2` (`zest-protocol`/v1 is dead, reports TVL 0).
   - `plume` / `somnia` were never protocols — they are **chains**. Added a
     `kind: chain` field; chain entries fetch `/v2/historicalChainTvl/{name}`
     (slug = chain name, e.g. `Plume Mainnet`, `Somnia`). See `defillama.py`
     `_fetch_chain_tvl`.
   - `morpho`, `euler`, `silo-finance`, `hydration` confirmed correct.

Also fixed a reporting bug: re-running on the same day appended duplicate rows
to the TVL/competitor tables because the report selected *all* rows for the
date. `reporting.py` now keeps the newest row per slug (`MAX(id) GROUP BY slug`).

## What works today (verified locally, no network)
- `run` / `report` / `export` all work and **never crash on a failed source**
  (failures are recorded in the report + `raw_cache` table).
- Valuation maths, scoring model (incl. ≥7d trend gate), config loading, TVL
  routing + dedup, the DIA-API / feed-coverage / Lasernet collectors, the EVM
  oracle poller, the grant funnel, the WoW alerts, and CSV export are covered by
  **44 passing pytest tests** (no network needed).
- Full report rendering confirmed with seeded data (all 10 sections, absolute +
  relative valuation scenarios, score breakdown).

## Architecture map (where to change things)
```
dia_alpha_monitor/
  cli.py          # argparse: run / report / export; orchestrates collection
  http_client.py  # the ONLY network path: timeout + retry + graceful failure + cache
  coingecko.py    # DIA market + competitors (free /coins/markets)
  dia_api.py      # DIA's OWN API (api.diadata.org): signed self-price + coverage
                  #   (quoted assets / exchange sources) + price-divergence check
  feed_activity.py# daily feed-coverage snapshot + RWA-vs-crypto split (v2)
  evm_oracle.py   # on-chain oracle update polling via public RPC (v2)
  lasernet.py     # Lasernet rollup throughput via Blockscout API — real usage (v2)
  grants.py       # grant funnel: conversion rates + stale-grant flags (v2)
  alerts.py       # week-over-week >10% movement [ALERT]s (v2)
  defillama.py    # per-protocol AND per-chain (kind: chain) TVL + compute_proxy()
  config_loader.py# loads config/*.yaml + derives grants/news/staking metrics
  scoring.py      # transparent 0–100 score; CATEGORY_MAX weights; NEUTRAL_FRACTION
  valuation.py    # pure functions: market-cap + relative scenarios (unit-tested)
  reporting.py    # single source of truth for derived numbers + rich rendering
  db.py           # SQLite schema + append-only snapshots + raw_cache
  models.py       # dataclasses + constants (DIA id, holding=500k, avg cost 0.18, scenarios)
config/*.yaml     # all manual inputs (ship with labelled EXAMPLE placeholders)
dashboard.py      # optional: streamlit run dashboard.py
tests/            # test_valuation.py, test_scoring.py, test_pipeline.py
```

Key design rules to preserve:
- **TVL is a "DIA-linked proxy", never call it official DIA TVS.** It's the TVL
  of watchlisted protocols. Labelled as a proxy everywhere it appears.
- **Missing data is scored at a neutral 40% baseline + flagged as a data gap**,
  not zero, so the headline number isn't dominated by empty manual files.
- Personal position (500,000 DIA @ ~$0.18, staked) lives in `models.py`.
- Everything is **research signals, not financial advice.**
- **Trusted-sources policy (added 2026-06-12):** every config `evidence_url`
  and `source` must be a *fully trusted* source — DIA's own properties
  (`diadata.org`, `docs.diadata.org`, `forum.diadata.org`, `api.diadata.org`,
  DIA GitHub) or the canonical free data APIs already used (CoinGecko,
  DeFiLlama). No third-party news/aggregators (CoinMarketCap, crypto news
  blogs, Medium). `dia_api.py` is the embodiment of this — DIA's own signed
  data. Report section "1b" cross-checks DIA's self-price vs CoinGecko as a
  data-integrity signal (currently ~0.2% divergence — sources agree).

## Suggested next steps
- [x] Run live, fix wrong CoinGecko ids / DeFiLlama slugs (done 2026-06-12).
- [x] Replace the `EXAMPLE` placeholder rows in `config/grants.yaml`,
      `news.yaml`, `staking_snapshots.yaml` with verified, source-linked entries
      (done 2026-06-12 via web research — every row links a primary source).
- [x] Set real `dia_role` / `confidence` / `evidence_url` per watchlist protocol.
      All 8 verified against DIA's own integration announcements: Parallel &
      Hydration = primary_oracle/high; Morpho/Euler/Silo/Zest = secondary_oracle
      (Morpho/Euler/Silo kept confidence=low on purpose — DIA only secures
      *select* markets, so their multi-$B TVL is NOT DIA-attributable);
      Plume/Somnia = grant_recipient/low.
      NOTE on `confidence`: it now means "share of this protocol's TVL plausibly
      DIA-attributable", which is why oracle-agnostic giants stay LOW. See the
      header comment in `config/protocols.yaml`.
- [ ] Data is a point-in-time snapshot (researched 2026-06-12). Refresh the
      staking reading (APY recalibrates to ~5-6% on 2026-07-01) and add new
      grants/news as DIA ships them. `lasernet_tx_count` is left null — no
      public free endpoint found; wire one up if/when available.
- [ ] (Optional) Add a `doctor` subcommand: ping both APIs + resolve every
      configured id/slug and print a "resolved vs failed" table — makes the
      first live run self-diagnosing.
- [x] CI workflow running `pytest` (`.github/workflows/ci.yml`, uv, py3.11+3.12,
      offline tests) — added 2026-06-12.
- [x] On-chain usage signal: SOLVED via `lasernet.py` — Lasernet (DIA's oracle
      rollup) throughput from explorer.diadata.org Blockscout API (~313k tx/day).
      This is where oracle activity actually happens (the consumer-chain
      `evm_oracle.py` poller stays as a complementary signal; its seeded legacy
      addresses are quiet — add active production adapters if wanted).
- [x] RWA undercount: mitigated via `config/feeds.yaml` — DIA's published
      "20,000+ RWA assets" recorded as a labelled, sourced manual figure shown
      next to the live REST floor. DEEPER (not done): decode Lasernet oracle
      feed KEYS (e.g. "AAPL/USD") to classify RWA vs crypto precisely.
- [ ] v2 ideas remaining: RSS auto-ingest for the news tracker.
- [ ] Feed DIA-API/feed-coverage signals into the 0–100 score (currently shown
      but not scored — would need a deliberate weight rebalance).

## Conventions
- PR #1 is merged into `main`. Develop on `claude/friendly-hawking-2tu1jf`.
- `git push -u origin claude/friendly-hawking-2tu1jf` (retry w/ backoff on
  network errors). Do not push to other branches. Do not open a new PR.
