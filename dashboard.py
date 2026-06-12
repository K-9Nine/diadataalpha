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

from dia_alpha_monitor import reporting, valuation
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
