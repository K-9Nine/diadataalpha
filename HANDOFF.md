# Handoff — dia-alpha-monitor

> Pick-up doc for a fresh Claude Code session (or a human). Read this first.
> Last updated 2026-06-13.

## TL;DR
- **What it is:** a local Python tool answering one question — *is DIA Data
  evolving from a governance token into usage-based oracle infrastructure, and
  is it a buy?* It collects market, on-chain, adoption and competitor signals
  into SQLite and prints a transparent 0–100 "alpha score" + investor report.
- **Status:** **fully built, merged to `main`, CI green, 56 passing tests.**
  v1 + v2 + RSS ingest + history backfill + TVS recalibration + DefiLlama Pro
  integration are all merged (PRs #1–#7).
- **Repo:** `K-9Nine/diadataalpha`. Default branch `main` has everything.
- **Latest investment read** (2026-06-13, see `ANALYSIS.md`): **speculative
  accumulate** at ~$0.12. Fair-value range **~$0.30–0.62 (base, 2.5–5×)**, bull
  ~$1.20, floor ~$0.10. Verdict hinges on the usage→fees link.

## ⭐ THE #1 NEXT ACTION — finish the DefiLlama Pro hook-up
The user **has a DefiLlama Pro API key** and the integration is built but **not
yet validated against a live key**. To finish it:

1. Confirm `DEFILLAMA_API_KEY` is set in the environment (it's read from the env;
   it should have been added via the environment's variable/secret settings, and
   env vars only apply in a **newly-started session** — so this session must be
   the new one). Check **without printing the value**:
   `[ -n "$DEFILLAMA_API_KEY" ] && echo set || echo missing`
2. Run `python -m dia_alpha_monitor run`. Look for the line
   `Oracle TVS (Pro): ok N days, latest $...`.
3. **Verify the parser.** The `/api/oracles` JSON shape was *unverified* at build
   time, so `defillama_pro._extract_oracle_series` handles two shapes defensively
   and caches the raw payload to the `raw_cache` table (`source='defillama_pro'`).
   If TVS does **not** populate (`oracle 'DIA' not found...`), inspect the raw
   response: `SELECT payload FROM raw_cache WHERE source='defillama_pro' ORDER BY id DESC LIMIT 1;`
   and adjust the parser to the real shape — it's a one-line fix.
4. Once live, the report §3 switches from the manual $148M figure to live TVS +
   a **real 7d/30d TVS-growth trend**, which also drives the alpha score's
   `tvl_growth` category. Also attempts DIA fees (`/api/summary/fees/dia`) —
   likely 404 (oracles aren't usually in the fees dataset); that's expected.

## Quick start
```bash
cd diadataalpha
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'              # add ,dashboard for Streamlit
python -m dia_alpha_monitor run         # live APIs; backfills 31d/90d history
python -m dia_alpha_monitor report
python -m pytest                        # expect 56 passed (no network needed)
```
Connectivity needs the open-internet egress policy (applied at container start).
If you see `403 Host not in allowlist`, the policy didn't apply to this session.

## The investment answer (current data, 2026-06-13)
- Price $0.1223, mcap **$14.65M**, FDV $20.66M (circ 119.68M / total 168.82M).
- **Official DIA oracle TVS (DefiLlama): ~$148.23M** → mcap/TVS **0.10×**.
  Concentrated in Zest (~48%). This is the REAL secured value.
- **Lasernet throughput +45% over 30d** — the strongest usage-growth signal.
- Coverage: 5,859 crypto feeds, 102 chains, 83 active scrapers; 20,000+ RWA
  (DIA-reported). Staking 4.4M DIA, 11 feeders, 12.56% APY (→5–6% Jul 1).
- DIA vs peers: 0.26% of Chainlink, ~5% of Pyth, ~37% of RedStone, ~40% of API3.
- Verdict: asymmetric speculative buy — cheap vs peers + growing usage, but
  small absolute scale ($148M TVS) and **monetisation (fees) still unproven**.

## Architecture map (where to change things)
```
dia_alpha_monitor/
  cli.py          # argparse: run / report / export; orchestrates collection
  http_client.py  # ONLY network path: get_json / get_text / post_json — timeout,
                  #   retry, graceful (None,err), optional raw_cache
  coingecko.py    # DIA market + competitors + fetch_market_chart (90d history)
  dia_api.py      # DIA's OWN API: signed self-price + coverage + divergence
  feed_activity.py# daily feed-coverage snapshot + RWA-vs-crypto split
  defillama.py    # per-protocol AND per-chain (kind: chain) TVL "reach" proxy
  defillama_pro.py# Pro API: OFFICIAL oracle TVS series + DIA fees (needs key)
  lasernet.py     # Lasernet rollup throughput + 31d history (real usage)
  evm_oracle.py   # on-chain oracle update polling via public RPC
  rss_ingest.py   # RSS auto-ingest of DIA blog -> ingested_news (dedup by URL)
  grants.py       # grant funnel: conversion rates + stale-grant flags
  alerts.py       # week-over-week >10% [ALERT]s (gated on >=7d history)
  config_loader.py# loads config/*.yaml + grants/news/staking metrics
  scoring.py      # 0–100 score; CATEGORY_MAX weights; >=7d trend gate
  valuation.py    # market-cap + relative scenarios (pure, unit-tested)
  reporting.py    # SINGLE source of truth for derived numbers + rich rendering;
                  #   *_block() builders; merged_news(); oracle_tvs_block()
  db.py           # SQLite schema; insert/upsert/latest/latest_value/
                  #   nearest_before/history_span_days; all_rows ORDER BY rowid
  models.py       # dataclasses + constants (DIA ids, holding=500k @ 0.18)
config/*.yaml     # manual inputs — all VERIFIED & source-linked (not examples)
dashboard.py      # optional: streamlit run dashboard.py
ANALYSIS.md       # the scrutinizable investment summary
tests/            # 56 tests, fully offline
```

## Config files (all verified/source-linked; trusted-sources policy applies)
`protocols.yaml` (TVL-proxy watchlist + dia_role/confidence), `competitors.yaml`,
`grants.yaml`, `news.yaml`, `staking_snapshots.yaml`, `oracles.yaml` (EVM RPC +
oracle addresses), `feeds.yaml` (manual RWA count), `news_feeds.yaml` (RSS),
`oracle_tvs.yaml` (manual official-TVS fallback used when no Pro key).

## Key design rules to preserve
- **The TVL "proxy" is watchlist REACH, NOT secured value.** It sums whole-
  protocol TVL of DIA users (~$11B) and overstates the real ~$148M oracle TVS by
  ~76×. The report §3 leads with official TVS and labels the proxy accordingly —
  never present the proxy as TVS.
- **Trusted-sources policy:** every config `evidence_url`/`source` is a DIA-
  official property or a canonical data API (CoinGecko / DeFiLlama). No third-
  party news/aggregators.
- **Graceful failure everywhere** — a dead source/slug/RPC/key is recorded, never
  crashes a run. Missing data is neutral-scored + flagged, not zeroed.
- **Trend metrics need ≥7d history** → show INSUFFICIENT DATA, not a misleading 0%.
- Personal position (500,000 DIA @ ~$0.18) lives in `models.py` (PnL only).
- Everything is **research signals, not financial advice.**

## Conventions
- Develop on a fresh `claude/<topic>` branch off `main`; open a PR; the user
  merges (CI must be green — workflow runs `pytest` on py3.11+3.12 via `uv`).
- Do **not** open a PR unless asked. Do **not** commit secrets (`.env` is
  gitignored). Keep the model identifier out of commits/PRs.
- CI gotcha (already fixed): use `uv venv` + `uv run pytest`, never
  `uv pip install --system` (PEP-668 fails on GitHub runners).

## Open / next steps
- [ ] **Validate the DefiLlama Pro `/api/oracles` parse on a live key** (see #1).
- [ ] Once live TVS history accrues, the `tvl_growth` score uses REAL TVS growth.
- [ ] Optional: a `doctor` subcommand (ping APIs + resolve every id/slug).
- [ ] Maintenance: refresh `staking_snapshots.yaml` after the 2026-07-01 APY
      recalibration; keep `oracle_tvs.yaml` current if running without the key.
- [ ] Deeper RWA: decode Lasernet oracle feed keys (e.g. `AAPL/USD`) to classify
      RWA vs crypto precisely (current live RWA count is a floor).
