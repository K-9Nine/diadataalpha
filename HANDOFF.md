# Handoff — dia-alpha-monitor

> Pick-up doc for a fresh Claude Code session (or a human). Read this first.

## TL;DR
- **What it is:** a local Python tool that collects DIA Data / DIA Oracles
  signals (market, DIA-linked TVL proxy, grants, RWA news, staking, competitors)
  into SQLite and prints a transparent 0–100 "alpha score" + investor report.
- **Status:** v1 is **built, tested (27 passing), committed, and pushed.**
- **Branch:** `claude/dia-alpha-monitor-build-8p1br6`
- **PR:** `K-9Nine/diadataalpha#1` — push to the branch to update it. Do **not**
  open a new PR.
- **Repo:** `K-9Nine/diadataalpha` (this is the target repo; `answergraph3` is unrelated).

## The one open blocker
Live API data was **never validated against the real endpoints** because the
previous session's network egress proxy blocked all outbound hosts
(`Host not in allowlist`, even `example.com`). The user has since opened full
internet access, BUT **egress policy is applied at container start**, so it only
takes effect in a **new session**. You are (hopefully) that new session.

### First thing to do in the new session
```bash
cd diadataalpha
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'
python -m dia_alpha_monitor run        # should now hit live APIs
python -m dia_alpha_monitor report
python -m pytest                       # expect 27 passed
```
Confirm connectivity quickly if unsure:
```bash
python -c "import httpx;print(httpx.get('https://api.coingecko.com/api/v3/ping',timeout=15).status_code)"
```
If you still get `403 Host not in allowlist`, the policy hasn't applied — tell
the user the environment still needs the open-internet policy and that it only
applies to newly-started sessions.

## Validation tasks once live data flows
These are best-guess identifiers I could not verify without network. On the
first live `run`, check the per-row status in the report and fix any that error:

1. **DIA CoinGecko id** = `dia-data` (in `dia_alpha_monitor/models.py`,
   `DIA_COINGECKO_ID`). If the market row is empty/STALE, the id is wrong —
   find the right one via `https://api.coingecko.com/api/v3/coins/list`.
2. **Competitor `coingecko_id`s** in `config/competitors.yaml` — especially
   `redstone-oracles` (uncertain). An empty markets row = wrong id. Chronicle
   intentionally has no token (`coingecko_id: null`) and shows as a data gap.
3. **DeFiLlama slugs** in `config/protocols.yaml` — `silo-finance`,
   `zest-protocol`, `parallel`, `plume`, `somnia`, `hydration` are guesses.
   A wrong slug shows as a per-row error (does NOT crash). Verify each at
   `https://defillama.com/protocol/<slug>` and correct the YAML.

After fixing ids/slugs, re-run `run` and the report should populate fully.

## What works today (verified locally, no network)
- `run` / `report` / `export` all work and **never crash on a failed source**
  (failures are recorded in the report + `raw_cache` table).
- Valuation maths, scoring model, config loading, TVL-proxy aggregation, and CSV
  export are covered by **27 passing pytest tests** (no network needed).
- Full report rendering confirmed with seeded data (all 10 sections, absolute +
  relative valuation scenarios, score breakdown).

## Architecture map (where to change things)
```
dia_alpha_monitor/
  cli.py          # argparse: run / report / export; orchestrates collection
  http_client.py  # the ONLY network path: timeout + retry + graceful failure + cache
  coingecko.py    # DIA market + competitors (free /coins/markets)
  defillama.py    # per-protocol TVL + compute_proxy() (gross + confidence-weighted)
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

## Suggested next steps (not yet done)
- [ ] Run live, fix any wrong CoinGecko ids / DeFiLlama slugs (see above).
- [ ] Replace the `EXAMPLE` placeholder rows in `config/grants.yaml`,
      `news.yaml`, `staking_snapshots.yaml` with verified entries.
- [ ] (Optional) Add a `doctor` subcommand: ping both APIs + resolve every
      configured id/slug and print a "resolved vs failed" table — makes the
      first live run self-diagnosing.
- [ ] (Optional, offered) Subscribe to PR #1 activity to autofix CI / respond to
      review comments. Add a CI workflow that runs `pytest` first.
- [ ] v2 ideas: RSS auto-ingest for the news tracker; an on-chain collector for
      *actual* DIA oracle reads/fees (the real usage signal behind the proxy).

## Conventions
- Develop on `claude/dia-alpha-monitor-build-8p1br6`; push updates PR #1.
- `git push -u origin claude/dia-alpha-monitor-build-8p1br6` (retry w/ backoff on
  network errors). Do not push to other branches. Do not open a new PR.
