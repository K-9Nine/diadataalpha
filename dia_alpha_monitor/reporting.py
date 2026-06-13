"""Assemble and render the investor report.

This module is the single source of truth for *derived* numbers (changes,
ratios, the alpha score). Both ``run`` (to persist the score) and ``report``
(to display) call into here, so the displayed report always matches what was
scored.

All rendering uses ``rich``. Proxy/manual/stale data is explicitly labelled.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dia_alpha_monitor import (
    alerts,
    config_loader,
    dia_api,
    grants as grant_analysis,
    rss_ingest,
    scoring,
    valuation,
)
from dia_alpha_monitor.db import Database
from dia_alpha_monitor.models import (
    DIA_COINGECKO_ID,
    USER_AVG_COST_USD,
    USER_HOLDING_DIA,
)


# -- small formatting helpers ---------------------------------------------

def _money(v: Optional[float], dp: int = 0) -> str:
    if v is None:
        return "n/a"
    if abs(v) >= 1_000_000_000:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1_000_000:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1e3:.1f}K"
    return f"${v:,.{dp}f}"


def _price(v: Optional[float]) -> str:
    return "n/a" if v is None else f"${v:,.4f}"


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:+.1f}%"


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / old * 100.0


# -- derived metric builders ----------------------------------------------

def market_block(db: Database) -> dict[str, Any]:
    row = db.latest("market_snapshots")
    if row is None:
        return {"present": False}
    vol_mcap = None
    if row["volume_24h"] and row["market_cap"]:
        vol_mcap = row["volume_24h"] / row["market_cap"]
    return {
        "present": True,
        "price": row["price"],
        "market_cap": row["market_cap"],
        "volume_24h": row["volume_24h"],
        "circulating_supply": row["circulating_supply"],
        "total_supply": row["total_supply"],
        "fdv": row["fdv"],
        "change_1d": row["change_1d"],
        "change_7d": row["change_7d"],
        "change_30d": row["change_30d"],
        "vol_mcap_ratio": vol_mcap,
        "stale": bool(row["stale"]),
        "date": row["date"],
    }


def dia_oracle_block(db: Database) -> dict[str, Any]:
    """Latest reading from DIA's own API (self-price + coverage stats)."""
    row = db.latest("dia_oracle_snapshots")
    if row is None:
        return {"present": False}
    return {
        "present": True,
        "dia_price": row["dia_price"],
        "dia_price_yesterday": row["dia_price_yesterday"],
        "volume_yesterday_usd": row["volume_yesterday_usd"],
        "quoted_assets": row["quoted_assets"],
        "exchange_sources": row["exchange_sources"],
        "active_scrapers": row["active_scrapers"],
        "signed": bool(row["signature"]),
        "error": row["error"],
        "date": row["date"],
    }


def tvl_block(db: Database) -> dict[str, Any]:
    proxy = db.latest("tvl_proxy")
    weekly = monthly = None
    # Trend changes are only trustworthy with >= 7 days of history; below that
    # we report INSUFFICIENT DATA instead of a misleading ~0% (see scoring.py).
    history_days = db.history_span_days("tvl_proxy")
    enough_history = history_days >= scoring.MIN_TREND_HISTORY_DAYS
    if proxy is not None and enough_history:
        prev_7d = db.nearest_before("tvl_proxy", 7, "gross_tvl")
        prev_30d = db.nearest_before("tvl_proxy", 30, "gross_tvl")
        weekly = _pct_change(proxy["gross_tvl"], prev_7d)
        monthly = _pct_change(proxy["gross_tvl"], prev_30d)
    # latest per-protocol snapshots from the most recent run date. The table is
    # append-only, so a second run on the same day writes a fresh row per slug;
    # keep only the newest (MAX(id)) row per slug to avoid duplicate listings.
    protocols: list[dict] = []
    if proxy is not None:
        rows = db.conn.execute(
            "SELECT * FROM tvl_snapshots WHERE id IN ("
            "  SELECT MAX(id) FROM tvl_snapshots WHERE date = ? GROUP BY slug"
            ") ORDER BY tvl DESC NULLS LAST",
            (proxy["date"],),
        ).fetchall()
        protocols = [dict(r) for r in rows]
    return {
        "present": proxy is not None,
        "gross_tvl": proxy["gross_tvl"] if proxy else None,
        "confidence_weighted_tvl": proxy["confidence_weighted_tvl"] if proxy else None,
        "n_protocols": proxy["n_protocols"] if proxy else 0,
        "n_resolved": proxy["n_resolved"] if proxy else 0,
        "weekly_change": weekly,
        "monthly_change": monthly,
        "protocols": protocols,
        "date": proxy["date"] if proxy else None,
        "history_days": history_days,
        "insufficient_history": proxy is not None and not enough_history,
    }


def feed_activity_block(db: Database) -> dict[str, Any]:
    """Latest DIA feed-coverage snapshot (total/RWA/crypto/chains/sources)."""
    row = db.latest("feed_activity_snapshots")
    if row is None:
        return {"present": False}
    return {
        "present": True,
        "total_feeds": row["total_feeds"],
        "rwa_feeds": row["rwa_feeds"],
        "crypto_feeds": row["crypto_feeds"],
        "n_blockchains": row["n_blockchains"],
        "active_sources": row["active_sources"],
        "error": row["error"],
        "date": row["date"],
    }


def lasernet_block(db: Database) -> dict[str, Any]:
    """Latest Lasernet throughput + 7d/30d daily-tx trend from backfilled history."""
    row = db.latest("lasernet_snapshots")
    if row is None:
        return {"present": False}
    # Real trend comes from the backfilled daily-tx chart (lasernet_history),
    # which spans ~31 days from run #1 — no need to wait for our own snapshots.
    wow_today = monthly = None
    hist_days = db.history_span_days("lasernet_history")
    latest_daily = db.latest_value("lasernet_history", "transactions_count")
    if latest_daily is not None and hist_days >= scoring.MIN_TREND_HISTORY_DAYS:
        wow_today = _pct_change(latest_daily, db.nearest_before("lasernet_history", 7, "transactions_count"))
        monthly = _pct_change(latest_daily, db.nearest_before("lasernet_history", 30, "transactions_count"))
    return {
        "present": True,
        "total_transactions": row["total_transactions"],
        "transactions_today": row["transactions_today"],
        "total_blocks": row["total_blocks"],
        "total_addresses": row["total_addresses"],
        "latest_daily_tx": latest_daily,
        "history_days": hist_days,
        "wow_today": wow_today,
        "monthly": monthly,
        "error": row["error"],
        "date": row["date"],
    }


def oracle_activity_block(db: Database) -> dict[str, Any]:
    """Latest on-chain oracle-activity reading per configured chain."""
    rows = db.conn.execute(
        "SELECT * FROM oracle_activity_snapshots WHERE id IN ("
        "  SELECT MAX(id) FROM oracle_activity_snapshots GROUP BY chain"
        ") ORDER BY chain ASC"
    ).fetchall()
    chains = [dict(r) for r in rows]
    total = sum(c["update_count"] or 0 for c in chains)
    return {"present": bool(chains), "chains": chains, "total_updates": total}


def competitor_block(db: Database) -> dict[str, Any]:
    latest = db.latest("competitor_snapshots")
    rows: list[dict] = []
    if latest is not None:
        cur = db.conn.execute(
            "SELECT * FROM competitor_snapshots WHERE id IN ("
            "  SELECT MAX(id) FROM competitor_snapshots WHERE date = ? GROUP BY slug"
            ") ORDER BY market_cap DESC NULLS LAST",
            (latest["date"],),
        )
        rows = [dict(r) for r in cur.fetchall()]
    leading = None
    for r in rows:
        if r.get("market_cap"):
            if leading is None or r["market_cap"] > leading["market_cap"]:
                leading = r
    return {"present": bool(rows), "competitors": rows, "leading": leading}


def _norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def merged_news(db: Database, config_news: list[dict]) -> list[dict]:
    """Combine manual config news with RSS-ingested items (manual wins on URL)."""
    seen = {_norm_url(n.get("url", "")) for n in config_news if n.get("url")}
    combined = list(config_news)
    for item in rss_ingest.load_ingested(db):
        if _norm_url(item.get("url", "")) in seen:
            continue
        item = dict(item)
        item["ingested"] = True
        item.setdefault("notes", "auto-ingested via RSS")
        combined.append(item)
    return combined


def compute_alpha(db: Database) -> dict[str, Any]:
    """Build the full category breakdown + total from current DB + configs."""
    market = market_block(db)
    tvl = tvl_block(db)
    comp = competitor_block(db)

    grants, _ = config_loader.load_grants()
    news, _ = config_loader.load_news()
    news = merged_news(db, news)  # fold in RSS-ingested items (manual wins)
    staking_raw, _ = config_loader.load_staking()
    gm = config_loader.grants_metrics(grants)
    nm = config_loader.news_metrics(news)
    sm = config_loader.staking_metrics(staking_raw)

    # relative discount vs the largest competitor we have data for
    best_discount = None
    if comp["leading"] and market.get("market_cap"):
        best_discount = valuation.relative_discount(
            market["market_cap"], comp["leading"]["market_cap"]
        )

    cats = [
        scoring.score_momentum(
            market.get("change_7d"), market.get("change_30d"), market.get("vol_mcap_ratio")
        ),
        scoring.score_tvl_growth(
            tvl.get("weekly_change"),
            tvl.get("monthly_change"),
            tvl.get("n_resolved", 0),
            history_days=tvl.get("history_days"),
        ),
        scoring.score_grants(gm["new_30d"], gm["mainnet"], gm["total"]),
        scoring.score_rwa(gm["rwa"], nm["rwa_recent_30d"], nm["rwa_total"]),
        scoring.score_staking(
            sm["delta_staked"], sm["delta_feeders"], sm["delta_tx"], sm["latest"] is not None
        ),
        scoring.score_valuation_discount(best_discount),
    ]
    agg = scoring.aggregate(cats)
    agg["best_discount"] = best_discount
    agg["grants_metrics"] = gm
    agg["news_metrics"] = nm
    agg["staking_metrics"] = sm
    agg["grant_funnel"] = grant_analysis.grant_funnel(grants)
    return agg


def changes_since_last(db: Database) -> dict[str, list[str]]:
    """Diff the two most recent score snapshots into bullish/bearish lists."""
    latest = db.latest("score_snapshots")
    prev = db.previous("score_snapshots")
    bullish: list[str] = []
    bearish: list[str] = []
    if latest is None or prev is None:
        return {"bullish": bullish, "bearish": bearish, "have_prev": False}
    try:
        a = {c["category"]: c for c in json.loads(latest["breakdown_json"])}
        b = {c["category"]: c for c in json.loads(prev["breakdown_json"])}
    except (TypeError, ValueError):
        return {"bullish": bullish, "bearish": bearish, "have_prev": False}
    for cat, cur in a.items():
        old = b.get(cat)
        if not old:
            continue
        delta = cur["points"] - old["points"]
        if delta >= 0.5:
            bullish.append(f"{cat}: {old['points']:.1f} -> {cur['points']:.1f} (+{delta:.1f})")
        elif delta <= -0.5:
            bearish.append(f"{cat}: {old['points']:.1f} -> {cur['points']:.1f} ({delta:.1f})")
    total_delta = latest["total"] - prev["total"]
    summary = f"overall {prev['total']:.1f} -> {latest['total']:.1f} ({total_delta:+.1f})"
    return {"bullish": bullish, "bearish": bearish, "have_prev": True, "summary": summary}


# -- valuation context -----------------------------------------------------

def valuation_block(db: Database, market: dict[str, Any], comp: dict[str, Any]) -> dict[str, Any]:
    circ = market.get("circulating_supply")
    price = market.get("price")
    mc_rows = valuation.market_cap_scenarios(circ, current_price=price)
    rel: list[dict] = []
    for c in comp.get("competitors", []):
        if c.get("market_cap") and c.get("name", "").lower() in {
            "chainlink",
            "pyth",
            "pyth network",
            "redstone",
        }:
            rel.extend(
                valuation.relative_scenarios(
                    c["name"], c["market_cap"], market.get("market_cap"), circ
                )
            )
    return {"market_cap_scenarios": mc_rows, "relative_scenarios": rel}


# -- persistence used by `run` --------------------------------------------

def persist_score(db: Database, agg: dict[str, Any]) -> None:
    from dia_alpha_monitor.models import today_str, utcnow

    db.insert(
        "score_snapshots",
        {
            "date": today_str(),
            "ts": utcnow().isoformat(),
            "total": agg["total"],
            "breakdown_json": json.dumps(agg["categories"]),
            "notes_json": json.dumps(agg.get("data_gaps", [])),
        },
    )


# -- rendering -------------------------------------------------------------

def print_report(console: Console, db: Database, warnings: list[str] | None = None) -> None:
    market = market_block(db)
    tvl = tvl_block(db)
    comp = competitor_block(db)
    agg = compute_alpha(db)
    changes = changes_since_last(db)
    val = valuation_block(db, market, comp)
    gm = agg["grants_metrics"]
    nm = agg["news_metrics"]
    sm = agg["staking_metrics"]

    console.rule("[bold cyan]DIA Alpha Monitor — Investor Research Report")
    console.print(
        "[dim]Research signals only. Not financial advice. "
        "Proxy and manual data are labelled as such.[/dim]\n"
    )

    # [ALERT] — metrics that moved > 10% week-over-week (top of report)
    fired = alerts.week_over_week_alerts(db)
    if fired:
        def _fmt(v, kind):
            if v is None:
                return "n/a"
            if kind == "price":
                return _price(v)
            if kind == "money":
                return _money(v)
            return f"{v:,.0f}"
        lines = []
        for a in fired:
            arrow = "▲" if a["direction"] == "up" else "▼"
            lines.append(
                f"{arrow} [bold]{a['metric']}[/bold] {a['pct']:+.1f}% WoW  "
                f"({_fmt(a['old'], a['fmt'])} → {_fmt(a['new'], a['fmt'])})"
            )
        console.print(
            Panel("\n".join(lines), title="[ALERT] >10% week-over-week moves",
                  border_style="red")
        )

    # 1. Price & market cap
    if market.get("present"):
        stale = " [yellow](STALE)[/yellow]" if market.get("stale") else ""
        t = Table(title=f"1. DIA Price & Market Cap{stale}  ·  as of {market['date']}", expand=True)
        for col in ["Price", "Market Cap", "FDV", "Circ. Supply", "Total Supply", "Vol/MCap"]:
            t.add_column(col)
        t.add_row(
            _price(market["price"]),
            _money(market["market_cap"]),
            _money(market["fdv"]),
            f"{market['circulating_supply']:,.0f}" if market["circulating_supply"] else "n/a",
            f"{market['total_supply']:,.0f}" if market["total_supply"] else "n/a",
            f"{market['vol_mcap_ratio']:.3f}" if market["vol_mcap_ratio"] else "n/a",
        )
        console.print(t)
    else:
        console.print("[red]1. No market data captured yet — run `python -m dia_alpha_monitor run`.[/red]")

    # 1b. DIA's own API — self-reported (signed) price + coverage (primary source)
    oracle = dia_oracle_block(db)
    if oracle.get("present"):
        div = dia_api.price_divergence_pct(oracle["dia_price"], market.get("price"))
        sig = " [green]✓ signed[/green]" if oracle["signed"] else ""
        assets = f"{oracle['quoted_assets']:,}" if oracle["quoted_assets"] else "n/a"
        srcs = oracle["exchange_sources"] if oracle["exchange_sources"] is not None else "n/a"
        active = oracle["active_scrapers"] if oracle["active_scrapers"] is not None else "n/a"
        lines = (
            f"DIA self-reported price{sig}: [bold]{_price(oracle['dia_price'])}[/bold]   "
            f"vs CoinGecko market: {_price(market.get('price'))}   "
            f"divergence: {_pct(div)}\n"
            f"Coverage (primary source): [bold]{assets}[/bold] assets quoted · "
            f"[bold]{srcs}[/bold] exchange sources ({active} active scrapers)"
        )
        if oracle["error"]:
            lines += f"\n[yellow]partial: {oracle['error']}[/yellow]"
        console.print(
            Panel(
                lines,
                title="1b. DIA Oracle — self-reported & signed (source: api.diadata.org)",
                border_style="green",
            )
        )

    # 1c. Feed coverage by asset class (DIA's own API; snapshotted daily)
    feeds = feed_activity_block(db)
    if feeds.get("present"):
        total = feeds["total_feeds"]
        feeds_meta, _ = config_loader.load_feeds_meta()
        rwa_reported = feeds_meta.get("rwa_assets_reported")
        rwa_line = ""
        if rwa_reported:
            rwa_line = (
                f"\nRWA assets (DIA-reported, manual): [bold]{int(rwa_reported):,}+[/bold] "
                f"as of {feeds_meta.get('rwa_as_of','?')}  [dim]{feeds_meta.get('rwa_source','')}[/dim]"
            )
        fl = (
            f"Total feeds (live REST): [bold]{total:,}[/bold]   "
            f"crypto: {feeds['crypto_feeds']:,}   "
            f"RWA floor*: {feeds['rwa_feeds']}   "
            f"blockchains: {feeds['n_blockchains']}   "
            f"active sources: {feeds['active_sources']}"
            f"{rwa_line}\n"
            f"[dim]*live RWA is a floor — the free REST endpoint is crypto-token-centric; "
            f"DIA's full RWA/xReal catalogue isn't enumerated there (hence the manual figure).[/dim]"
        ) if total is not None else "[yellow]feed coverage unavailable[/yellow]"
        if feeds["error"]:
            fl += f"\n[yellow]partial: {feeds['error']}[/yellow]"
        console.print(Panel(fl, title="1c. Feed Coverage (source: api.diadata.org)", border_style="green"))

    # 2. Volume trend
    t = Table(title="2. Price / Volume Trend", expand=True)
    for col in ["1d", "7d", "30d", "24h Volume"]:
        t.add_column(col)
    t.add_row(
        _pct(market.get("change_1d")),
        _pct(market.get("change_7d")),
        _pct(market.get("change_30d")),
        _money(market.get("volume_24h")),
    )
    console.print(t)

    # 3. DIA oracle TVS (official) vs watchlist reach (the proxy)
    if tvl.get("insufficient_history"):
        change_line = (
            f"Weekly / 30d change: [yellow]INSUFFICIENT DATA[/yellow] "
            f"(need ≥{scoring.MIN_TREND_HISTORY_DAYS}d of history, "
            f"have {tvl.get('history_days', 0):.0f}d — run daily)"
        )
    else:
        change_line = (
            f"Weekly change: {_pct(tvl['weekly_change'])}   "
            f"30d change: {_pct(tvl['monthly_change'])}"
        )
    # Official TVS (manual, DefiLlama) anchors the proxy so it can't mislead.
    tvs_meta, _ = config_loader.load_oracle_tvs()
    tvs = tvs_meta.get("defillama_tvs_usd")
    official_line = ""
    if tvs:
        mcap = market.get("market_cap")
        mcap_tvs = f"{mcap / tvs:.2f}x" if mcap else "n/a"
        gross = tvl.get("gross_tvl") or 0
        overstate = f"~{gross / tvs:.0f}x" if tvs else "n/a"
        official_line = (
            f"[bold]OFFICIAL DIA oracle TVS (DefiLlama, {tvs_meta.get('as_of','?')}): "
            f"{_money(tvs)}[/bold]   mcap/TVS: {mcap_tvs}\n"
            f"  Top: {tvs_meta.get('top_protocols','?')}   [dim]{tvs_meta.get('source','')}[/dim]\n"
            f"[yellow]⚠ The 'reach' figures below sum WHOLE-protocol TVL of DIA users — an "
            f"UPPER BOUND, not secured value. They overstate real TVS {overstate}.[/yellow]\n─\n"
        )
    console.print(
        Panel(
            official_line
            + f"Watchlist reach (gross): [bold]{_money(tvl['gross_tvl'])}[/bold]   "
            f"confidence-weighted: [bold]{_money(tvl['confidence_weighted_tvl'])}[/bold]\n"
            f"{change_line}   "
            f"Resolved {tvl['n_resolved']}/{tvl['n_protocols']} protocols",
            title="3. DIA Oracle TVS (official) vs Watchlist Reach  ⚠ reach ≠ secured value",
            border_style="yellow",
        )
    )
    if tvl["protocols"]:
        pt = Table(show_header=True, expand=True)
        for col in ["Protocol", "TVL", "DIA role", "Conf.", "Status"]:
            pt.add_column(col)
        for p in tvl["protocols"]:
            status = "[red]" + (p["error"] or "")[:30] + "[/red]" if p.get("error") else "[green]ok[/green]"
            pt.add_row(
                p["name"],
                _money(p["tvl"]) if p["tvl"] is not None else "n/a",
                p["dia_role"],
                p["confidence"],
                status,
            )
        console.print(pt)

    # 3b. On-chain oracle activity (REAL usage signal, via public RPC)
    oa = oracle_activity_block(db)
    if oa.get("present"):
        ot = Table(
            title="3b. On-chain DIA Oracle Activity  ·  real usage signal (public RPC)",
            expand=True,
        )
        for col in ["Chain", "Oracle", "Updates (window)", "Blocks scanned", "Status"]:
            ot.add_column(col)
        for c in oa["chains"]:
            addr = (c["oracle_address"] or "")
            short = (addr[:10] + "…") if len(addr) > 12 else addr
            window = (
                f"{c['from_block']}–{c['to_block']}"
                if c.get("from_block") is not None and c.get("to_block") is not None
                else "n/a"
            )
            if c.get("error"):
                status = "[red]" + c["error"][:24] + "[/red]"
                updates = "n/a"
            else:
                status = "[green]ok[/green]"
                updates = f"{c['update_count']:,}" if c["update_count"] is not None else "n/a"
            ot.add_row(c["chain"], short, updates, window, status)
        console.print(ot)
        console.print(
            "[dim]0 updates can be legitimate — many legacy push-oracles are quiet under "
            "DIA's Lasernet pull model. Add active production addresses in config/oracles.yaml.[/dim]"
        )

    # 3c. Lasernet throughput — where DIA oracle activity actually happens
    lnet = lasernet_block(db)
    if lnet.get("present") and lnet["transactions_today"] is not None:
        if lnet["wow_today"] is not None:
            trend = (
                f"   daily-tx trend: 7d {_pct(lnet['wow_today'])}   "
                f"30d {_pct(lnet['monthly'])}  "
                f"[dim]({lnet['history_days']:.0f}d history)[/dim]"
            )
        else:
            trend = "   trend: [dim]INSUFFICIENT DATA (need ≥7d)[/dim]"
        console.print(
            Panel(
                f"Transactions today: [bold]{lnet['transactions_today']:,}[/bold]{trend}\n"
                f"Total transactions: {lnet['total_transactions']:,}   "
                f"blocks: {lnet['total_blocks']:,}   addresses: {lnet['total_addresses']:,}\n"
                f"[dim]Lasernet is DIA's oracle rollup — throughput ≈ oracle operations, "
                f"a direct trustless usage signal (vs the TVL proxy).[/dim]",
                title="3c. Lasernet Oracle Throughput (source: explorer.diadata.org)",
                border_style="green",
            )
        )

    # 4. New integrations / grants (+ funnel conversion analysis)
    funnel = agg.get("grant_funnel", {})
    fc = funnel.get("counts", {})
    to_test = funnel.get("to_testnet_rate")
    to_main = funnel.get("to_mainnet_rate")
    grants_lines = (
        f"Total grants: [bold]{gm['total']}[/bold]   Mainnet: {gm['mainnet']}   "
        f"RWA: {gm['rwa']}   Chains: {gm['n_chains']}   New (30d): [bold]{gm['new_30d']}[/bold]\n"
        f"Funnel: announced {fc.get('announced',0)} → testnet {fc.get('testnet',0)} → "
        f"mainnet {fc.get('mainnet',0)}"
        + (f"  (inactive {fc['inactive']})" if fc.get("inactive") else "")
        + "\n"
        f"Conversion: reached-testnet "
        f"{('%.0f%%' % (to_test*100)) if to_test is not None else 'n/a'}   "
        f"to-mainnet [bold]{('%.0f%%' % (to_main*100)) if to_main is not None else 'n/a'}[/bold]"
    )
    console.print(Panel(grants_lines, title="4. Grants & Adoption + Funnel (manual: config/grants.yaml)", border_style="cyan"))
    if gm["new_30d_items"]:
        for g in gm["new_30d_items"][:8]:
            console.print(
                f"  • [green]NEW[/green] {g.get('date_added','?')} — {g.get('chain','?')} / "
                f"{g.get('project','?')} ({g.get('status','?')}) {g.get('evidence_url','')}"
            )
    if funnel.get("stale"):
        console.print(
            f"  [yellow]⚠ {funnel['n_stale']} stale grant(s) >"
            f"{funnel['stale_days']}d pre-mainnet:[/yellow]"
        )
        for s in funnel["stale"][:6]:
            console.print(
                f"    · {s['chain']} / {s['project']} — {s['status']}, "
                f"{s['days']}d since {s['date_added']}"
            )

    # 5. RWA traction
    console.print(
        Panel(
            f"RWA grants: [bold]{gm['rwa']}[/bold]   RWA news items: {nm['rwa_total']}   "
            f"RWA news in last 30d: [bold]{nm['rwa_recent_30d']}[/bold]",
            title="5. RWA-specific Traction (manual: config/news.yaml + grants.yaml)",
            border_style="cyan",
        )
    )
    if nm["top_high_impact"]:
        console.print("[dim]  Top recent high-impact items ([cyan]rss[/cyan] = auto-ingested):[/dim]")
        for n in nm["top_high_impact"][:10]:
            tag = " [cyan]\\[rss][/cyan]" if n.get("ingested") else ""
            console.print(
                f"  • [{n.get('impact_score','?')}/5] {n.get('date','?')} "
                f"[{n.get('category','?')}]{tag} {n.get('title','?')}  {n.get('url','')}"
            )

    # 6. Staking / Lasernet
    if sm["latest"]:
        L = sm["latest"]
        flags = []
        if sm["delta_staked"] and sm["delta_staked"] > 0:
            flags.append("[green]staked supply rising[/green]")
        if sm["delta_feeders"] and sm["delta_feeders"] > 0:
            flags.append("[green]new feeders[/green]")
        if sm["delta_apy"] is not None and sm["delta_apy"] != 0:
            flags.append(f"APY change {sm['delta_apy']:+.2f}")
        if sm["delta_tx"] and sm["delta_tx"] > 0:
            flags.append("[green]Lasernet tx spike[/green]")
        body = (
            f"Total DIA staked: [bold]{L.get('total_dia_staked','n/a')}[/bold]   "
            f"Feeders: {L.get('feeders','n/a')}   APY: {L.get('apy','n/a')}   "
            f"Lasernet tx: {L.get('lasernet_tx_count','n/a')}\n"
            f"As of {L.get('date','?')} — source: {L.get('source','?')}\n"
            f"Flags: {', '.join(flags) if flags else 'none / insufficient history'}"
        )
    else:
        body = "[yellow]No staking snapshot yet — add entries to config/staking_snapshots.yaml[/yellow]"
    console.print(Panel(body, title="6. Staking / Lasernet (manual snapshot)", border_style="magenta"))

    # 7. Competitor comparison
    if comp["present"]:
        ct = Table(title="7. Competitor Comparison", expand=True)
        for col in ["Oracle", "Market Cap", "24h Vol", "TVS (if public)", "DIA discount"]:
            ct.add_column(col)
        dia_mc = market.get("market_cap")
        for c in comp["competitors"]:
            disc = valuation.relative_discount(dia_mc, c.get("market_cap"))
            ct.add_row(
                c["name"],
                _money(c.get("market_cap")) if c.get("market_cap") else "n/a",
                _money(c.get("volume_24h")) if c.get("volume_24h") else "n/a",
                _money(c.get("tvs")) if c.get("tvs") else "n/a",
                f"{disc*100:.2f}%" if disc else ("[dim]" + (c.get("error","")[:24]) + "[/dim]" if c.get("error") else "n/a"),
            )
        console.print(ct)

    # 8. Valuation scenarios
    vt = Table(title="8. Valuation Scenarios (implied price + your 500k DIA position)", expand=True)
    for col in ["Target MCap", "Implied Price", "x vs now", "Your Holding", "PnL vs cost", "ROI"]:
        vt.add_column(col)
    for r in val["market_cap_scenarios"]:
        vt.add_row(
            _money(r["target_market_cap"]),
            _price(r["implied_price"]),
            f"{r['multiple_vs_now']:.1f}x" if r["multiple_vs_now"] else "n/a",
            _money(r["holding_value"]),
            _money(r["holding_pnl"]),
            f"{r['holding_roi']*100:.0f}%" if r["holding_roi"] is not None else "n/a",
        )
    console.print(vt)
    console.print(
        f"[dim]Position assumption: {USER_HOLDING_DIA:,.0f} DIA @ ~${USER_AVG_COST_USD} avg cost "
        f"(staked on Lasernet). Cost basis ≈ {_money(USER_HOLDING_DIA*USER_AVG_COST_USD)}.[/dim]"
    )
    if val["relative_scenarios"]:
        rt = Table(title="8b. Relative-to-competitor scenarios", expand=True)
        for col in ["If DIA reaches", "Of", "Target MCap", "Implied Price", "Upside"]:
            rt.add_column(col)
        for r in val["relative_scenarios"]:
            rt.add_row(
                f"{r['fraction']*100:.1f}%",
                r["competitor"],
                _money(r["target_market_cap"]),
                _price(r["implied_price"]),
                f"{r['upside_vs_now']:.1f}x" if r["upside_vs_now"] else "n/a",
            )
        console.print(rt)

    # 9. Alpha score
    st = Table(title=f"9. Alpha Score: {agg['total']:.1f} / {agg['max']}", expand=True)
    for col in ["Category", "Points", "Max", "Gap", "Rationale"]:
        st.add_column(col)
    for c in agg["categories"]:
        st.add_row(
            c["category"],
            f"{c['points']:.1f}",
            str(c["max"]),
            "[yellow]gap[/yellow]" if c.get("gap") else "",
            c["rationale"][:70],
        )
    console.print(st)
    if changes.get("have_prev"):
        console.print(f"[bold]Change since last run:[/bold] {changes.get('summary','')}")
        for b in changes["bullish"]:
            console.print(f"  [green]▲ bullish[/green] {b}")
        for b in changes["bearish"]:
            console.print(f"  [red]▼ bearish[/red] {b}")
    else:
        console.print("[dim]Change since last run: not enough history yet (need ≥2 runs).[/dim]")
    if agg["data_gaps"]:
        console.print(f"[yellow]Data gaps (neutral-scored): {', '.join(agg['data_gaps'])}[/yellow]")

    # 10. What would change my mind
    console.print(
        Panel(
            "[bold]Bull case confirmation — would RAISE conviction:[/bold]\n"
            "  • DIA-linked TVL proxy rising AND DIA publishing official TVS that corroborates it\n"
            "  • New mainnet grants converting to live, fee-generating oracle feeds\n"
            "  • Staked DIA supply + Feeder count rising; Lasernet tx count trending up\n"
            "  • Concrete RWA feeds (equities/ETF/commodities/PoR) going live with named users\n"
            "  • DIA relative discount vs Chainlink/Pyth narrowing on real usage, not just price\n\n"
            "[bold]Bear case / thesis-breakers — would LOWER conviction:[/bold]\n"
            "  • Integrations stay 'announced' with no measurable usage, fees or TVS\n"
            "  • Watchlist protocols are NOT actually using DIA (confidence stays low/unverified)\n"
            "  • Staked supply / Feeders flat or falling; Lasernet activity stagnant\n"
            "  • Token remains governance-only with no gas/staking demand growth\n"
            "  • Competitors capture the RWA-oracle narrative and integrations",
            title="10. What Would Change My Mind?",
            border_style="blue",
        )
    )

    if warnings:
        console.print("\n[yellow]Config / data warnings:[/yellow]")
        for w in warnings:
            console.print(f"  • {w}")
    console.print(
        "\n[bold]Manual checks required:[/bold] verify each protocol actually uses DIA oracles "
        "(update dia_role/confidence/evidence_url in config/protocols.yaml), keep grants.yaml, "
        "news.yaml and staking_snapshots.yaml current, and confirm CoinGecko ids in competitors.yaml."
    )
