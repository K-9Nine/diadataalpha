"""Command-line interface: ``run``, ``report``, ``export``.

The CLI orchestrates collectors and persistence but keeps *all* derived
maths in ``reporting``/``scoring``/``valuation`` so behaviour is identical
between commands and unit-testable.

A failure in any single data source is recorded and the run continues.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from rich.console import Console

from dia_alpha_monitor import coingecko, config_loader, defillama, reporting
from dia_alpha_monitor.db import Database
from dia_alpha_monitor.models import DIA_COINGECKO_ID, today_str, utcnow

console = Console()


def _open_db(args) -> Database:
    return Database(getattr(args, "db", None) or os.environ.get("DIA_DB_PATH", "dia_alpha_monitor.db"))


def cmd_run(args) -> int:
    load_dotenv()
    db = _open_db(args)
    warnings: list[str] = []
    console.rule("[bold cyan]dia-alpha-monitor run")

    # A. Market data ------------------------------------------------------
    cg_id = os.environ.get("DIA_COINGECKO_ID", DIA_COINGECKO_ID)
    market, merr = coingecko.fetch_market(cg_id, cache=db)
    if merr:
        warnings.append(f"CoinGecko market fetch failed: {merr}")
        console.print(f"[yellow]Market: FAILED ({merr}) — continuing[/yellow]")
    else:
        console.print(f"[green]Market: ok[/green] price={market.price} mcap={market.market_cap}")
    db.insert("market_snapshots", market.as_dict())

    # B. DeFiLlama protocol TVL proxy ------------------------------------
    protocols, pwarn = config_loader.load_protocols()
    if pwarn:
        warnings.append(pwarn)
    tvl_snaps = defillama.fetch_all_protocols(protocols, cache=db)
    for s in tvl_snaps:
        db.insert("tvl_snapshots", s.as_dict())
        tag = f"[red]err[/red] {s.error}" if s.error else f"[green]ok[/green] {s.tvl}"
        console.print(f"  TVL {s.name:<18} {tag}")
    proxy = defillama.compute_proxy(tvl_snaps)
    db.insert(
        "tvl_proxy",
        {
            "date": today_str(),
            "ts": utcnow().isoformat(),
            "gross_tvl": proxy["gross_tvl"],
            "confidence_weighted_tvl": proxy["confidence_weighted_tvl"],
            "n_protocols": proxy["n_protocols"],
            "n_resolved": proxy["n_resolved"],
        },
    )
    console.print(
        f"[green]DIA-linked TVL proxy (PROXY, not official TVS):[/green] "
        f"gross={proxy['gross_tvl']:,.0f} weighted={proxy['confidence_weighted_tvl']:,.0f} "
        f"({proxy['n_resolved']}/{proxy['n_protocols']} resolved)"
    )

    # F. Competitors ------------------------------------------------------
    competitors, cwarn = config_loader.load_competitors()
    if cwarn:
        warnings.append(cwarn)
    comp_snaps = coingecko.fetch_competitors(competitors, cache=db)
    for s in comp_snaps:
        db.insert("competitor_snapshots", s.as_dict())
        tag = f"[red]err[/red] {s.error}" if s.error else f"[green]ok[/green] {s.market_cap}"
        console.print(f"  COMP {s.name:<12} {tag}")

    # E. Ingest manual staking snapshots (so we keep change history) ------
    staking_raw, swarn = config_loader.load_staking()
    if swarn:
        warnings.append(swarn)
    sm = config_loader.staking_metrics(staking_raw)
    if sm["latest"]:
        L = sm["latest"]
        db.insert(
            "staking_snapshots",
            {
                "date": str(L.get("date", today_str())),
                "ts": utcnow().isoformat(),
                "total_staked": L.get("total_dia_staked"),
                "feeders": L.get("feeders"),
                "apy": L.get("apy"),
                "lasernet_tx_count": L.get("lasernet_tx_count"),
                "source": L.get("source", ""),
                "notes": L.get("notes", ""),
            },
        )

    # G. Score + persist --------------------------------------------------
    agg = reporting.compute_alpha(db)
    reporting.persist_score(db, agg)
    console.print(f"\n[bold]Alpha score:[/bold] {agg['total']:.1f}/100")
    if agg["data_gaps"]:
        console.print(f"[yellow]Data gaps: {', '.join(agg['data_gaps'])}[/yellow]")
    for w in warnings:
        console.print(f"[yellow]warning:[/yellow] {w}")
    console.print("\n[dim]Run complete. View the full report with: python -m dia_alpha_monitor report[/dim]")
    db.close()
    return 0


def cmd_report(args) -> int:
    load_dotenv()
    db = _open_db(args)
    warnings: list[str] = []
    for loader in (config_loader.load_protocols, config_loader.load_competitors,
                   config_loader.load_grants, config_loader.load_news, config_loader.load_staking):
        _, w = loader()
        if w:
            warnings.append(w)
    if db.latest("market_snapshots") is None:
        console.print("[red]No data yet. Run `python -m dia_alpha_monitor run` first.[/red]")
        db.close()
        return 1
    reporting.print_report(console, db, warnings=warnings)
    db.close()
    return 0


def cmd_export(args) -> int:
    import csv

    db = _open_db(args)
    out_dir = args.out or os.environ.get("DIA_EXPORT_DIR", "exports")
    os.makedirs(out_dir, exist_ok=True)
    tables = [
        "market_snapshots",
        "tvl_snapshots",
        "tvl_proxy",
        "competitor_snapshots",
        "staking_snapshots",
        "score_snapshots",
    ]
    written = []
    for table in tables:
        rows = db.all_rows(table)
        path = os.path.join(out_dir, f"{table}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            if rows:
                writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
                writer.writeheader()
                for r in rows:
                    writer.writerow(dict(r))
            else:
                fh.write("")
        written.append((path, len(rows)))
    for path, n in written:
        console.print(f"[green]exported[/green] {path} ({n} rows)")
    db.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dia_alpha_monitor",
        description="DIA Data / DIA Oracles alpha-signal research tool (research signals, not advice).",
    )
    p.add_argument("--db", help="Path to SQLite DB (default: dia_alpha_monitor.db)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Collect data and store snapshots").set_defaults(func=cmd_run)
    sub.add_parser("report", help="Print the investor research report").set_defaults(func=cmd_report)
    exp = sub.add_parser("export", help="Export tables to CSV in ./exports")
    exp.add_argument("--out", help="Output directory (default: exports)")
    exp.set_defaults(func=cmd_export)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - top-level safety net
        console.print(f"[red]Unexpected error: {type(exc).__name__}: {exc}[/red]")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
