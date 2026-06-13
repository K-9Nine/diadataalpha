"""Optional Streamlit dashboard.

Run with:  streamlit run dashboard.py

Reads the same SQLite store the CLI writes to. It does NOT collect data —
run `python -m dia_alpha_monitor run` first. Everything shown here is a
research signal, not financial advice; proxy/manual data is labelled.
"""

from __future__ import annotations

import json
import os

import pandas as pd

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Streamlit is not installed. Install the optional extra:\n"
        "  uv pip install -e '.[dashboard]'   (or)   pip install streamlit"
    )

from dia_alpha_monitor import alerts, dia_api, reporting, valuation
from dia_alpha_monitor.db import Database

DB_PATH = os.environ.get("DIA_DB_PATH", "dia_alpha_monitor.db")

st.set_page_config(page_title="DIA Alpha Monitor", layout="wide")
st.title("DIA Alpha Monitor")
st.caption("Research signals only — not financial advice. Proxy / manual data is labelled.")

if not os.path.exists(DB_PATH):
    st.error(f"No database at {DB_PATH}. Run `python -m dia_alpha_monitor run` first.")
    st.stop()

db = Database(DB_PATH)


def _df(table: str) -> pd.DataFrame:
    rows = db.all_rows(table)
    return pd.DataFrame([dict(r) for r in rows])


market = reporting.market_block(db)
tvl = reporting.tvl_block(db)
comp = reporting.competitor_block(db)
agg = reporting.compute_alpha(db)

if not market.get("present"):
    st.warning("No market data captured yet.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("DIA price", f"${market['price']:.4f}" if market["price"] else "n/a",
          f"{market.get('change_1d') or 0:+.1f}% (1d)")
c2.metric("Market cap", f"${(market['market_cap'] or 0)/1e6:.1f}M")
c3.metric("DIA-linked TVL proxy", f"${(tvl['gross_tvl'] or 0)/1e6:.1f}M",
          f"{tvl.get('weekly_change') or 0:+.1f}% (7d)")
c4.metric("Alpha score", f"{agg['total']:.1f}/100")

st.info("The TVL figure is a DIA-linked PROXY (TVL of watchlisted protocols), NOT official DIA TVS.")

oracle = reporting.dia_oracle_block(db)
if oracle.get("present"):
    st.subheader("DIA Oracle — self-reported & signed (source: api.diadata.org)")
    div = dia_api.price_divergence_pct(oracle["dia_price"], market.get("price"))
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("DIA self-price" + (" ✓signed" if oracle["signed"] else ""),
              f"${oracle['dia_price']:.4f}" if oracle["dia_price"] else "n/a")
    o2.metric("Divergence vs CoinGecko", f"{div:+.2f}%" if div is not None else "n/a")
    o3.metric("Assets quoted", f"{oracle['quoted_assets']:,}" if oracle["quoted_assets"] else "n/a")
    o4.metric("Active scrapers",
              f"{oracle['active_scrapers']}/{oracle['exchange_sources']}"
              if oracle["exchange_sources"] is not None else "n/a")
    st.caption("DIA's own signed price + coverage — a primary-source cross-check on the market data.")

# v2: feed coverage, on-chain oracle activity, week-over-week alerts
fired = alerts.week_over_week_alerts(db)
if fired:
    st.error("**[ALERT] >10% week-over-week:**  " + "   ".join(
        f"{'▲' if a['direction']=='up' else '▼'} {a['metric']} {a['pct']:+.1f}%" for a in fired
    ))

feeds = reporting.feed_activity_block(db)
if feeds.get("present") and feeds["total_feeds"] is not None:
    st.subheader("Feed coverage (source: api.diadata.org)")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Total feeds", f"{feeds['total_feeds']:,}")
    f2.metric("Crypto / RWA*", f"{feeds['crypto_feeds']:,} / {feeds['rwa_feeds']}")
    f3.metric("Blockchains", feeds["n_blockchains"])
    f4.metric("Active sources", feeds["active_sources"])
    st.caption("*RWA is a floor — the free REST endpoint is crypto-token-centric.")

lnet = reporting.lasernet_block(db)
if lnet.get("present") and lnet["transactions_today"] is not None:
    st.subheader("Lasernet oracle throughput (source: explorer.diadata.org)")
    l1, l2, l3 = st.columns(3)
    l1.metric("Transactions today", f"{lnet['transactions_today']:,}",
              f"{lnet['wow_today']:+.1f}% WoW" if lnet["wow_today"] is not None else None)
    l2.metric("Total transactions", f"{lnet['total_transactions']:,}")
    l3.metric("Addresses", f"{lnet['total_addresses']:,}")
    st.caption("Lasernet is DIA's oracle rollup — throughput ≈ oracle operations (real usage signal).")

oa = reporting.oracle_activity_block(db)
if oa.get("present"):
    st.subheader("On-chain DIA oracle activity (public RPC — real usage signal)")
    st.dataframe(pd.DataFrame(oa["chains"])[
        ["chain", "oracle_address", "update_count", "from_block", "to_block", "error"]
    ], use_container_width=True)
    st.caption("0 updates can be legitimate — legacy push-oracles are quiet under the Lasernet pull model.")

if agg.get("grant_funnel"):
    gfn = agg["grant_funnel"]
    rate = gfn.get("to_mainnet_rate")
    st.caption(
        f"Grant funnel — to-mainnet conversion: "
        f"{('%.0f%%' % (rate*100)) if rate is not None else 'n/a'}; "
        f"stale (>{gfn['stale_days']}d pre-mainnet): {gfn['n_stale']}"
    )

st.subheader("Alpha score breakdown")
st.dataframe(pd.DataFrame(agg["categories"]), use_container_width=True)
if agg["data_gaps"]:
    st.warning("Data gaps (neutral-scored): " + ", ".join(agg["data_gaps"]))

st.subheader("Market history")
mdf = _df("market_snapshots")
if not mdf.empty:
    st.line_chart(mdf.set_index("ts")[["price"]])

st.subheader("DIA-linked TVL proxy history")
pdf = _df("tvl_proxy")
if not pdf.empty:
    st.line_chart(pdf.set_index("ts")[["gross_tvl", "confidence_weighted_tvl"]])

st.subheader("Per-protocol TVL (latest run)")
st.dataframe(pd.DataFrame(tvl["protocols"]), use_container_width=True)

st.subheader("Competitors")
st.dataframe(pd.DataFrame(comp["competitors"]), use_container_width=True)

st.subheader("Valuation scenarios (your 500k DIA position)")
vrows = valuation.market_cap_scenarios(market.get("circulating_supply"), current_price=market.get("price"))
st.dataframe(pd.DataFrame(vrows), use_container_width=True)

st.subheader("Score history")
sdf = _df("score_snapshots")
if not sdf.empty:
    st.line_chart(sdf.set_index("ts")[["total"]])

db.close()
