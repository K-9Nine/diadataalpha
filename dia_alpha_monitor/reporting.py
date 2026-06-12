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

from dia_alpha_monitor import config_loader, dia_api, scoring, valuation
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
    if proxy is not None:
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
    }


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


def compute_alpha(db: Database) -> dict[str, Any]:
    """Build the full category breakdown + total from current DB + configs."""
    market = market_block(db)
    tvl = tvl_block(db)
    comp = competitor_block(db)

    grants, _ = config_loader.load_grants()
    news, _ = config_loader.load_news()
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
            tvl.get("weekly_change"), tvl.get("monthly_change"), tvl.get("n_resolved", 0)
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

    # 3. DIA-linked TVL proxy
    console.print(
        Panel(
            f"Gross DIA-linked TVL proxy: [bold]{_money(tvl['gross_tvl'])}[/bold]   "
            f"Confidence-weighted: [bold]{_money(tvl['confidence_weighted_tvl'])}[/bold]\n"
            f"Weekly change: {_pct(tvl['weekly_change'])}   "
            f"30d change: {_pct(tvl['monthly_change'])}   "
            f"Resolved {tvl['n_resolved']}/{tvl['n_protocols']} protocols",
            title="3. DIA-linked TVL Proxy  ⚠ PROXY — NOT official DIA TVS",
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

    # 4. New integrations / grants
    grants_lines = (
        f"Total grants: [bold]{gm['total']}[/bold]   Mainnet: {gm['mainnet']}   "
        f"RWA: {gm['rwa']}   Chains: {gm['n_chains']}   New (30d): [bold]{gm['new_30d']}[/bold]"
    )
    console.print(Panel(grants_lines, title="4. Grants & Adoption (manual: config/grants.yaml)", border_style="cyan"))
    if gm["new_30d_items"]:
        for g in gm["new_30d_items"][:8]:
            console.print(
                f"  • [green]NEW[/green] {g.get('date_added','?')} — {g.get('chain','?')} / "
                f"{g.get('project','?')} ({g.get('status','?')}) {g.get('evidence_url','')}"
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
        console.print("[dim]  Top recent high-impact items:[/dim]")
        for n in nm["top_high_impact"][:10]:
            console.print(
                f"  • [{n.get('impact_score','?')}/5] {n.get('date','?')} "
                f"[{n.get('category','?')}] {n.get('title','?')}  {n.get('url','')}"
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
