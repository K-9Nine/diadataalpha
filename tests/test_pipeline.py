"""Integration-ish tests for config loading, DB, proxy and CLI export.

These avoid the network: they exercise the pure/local paths only.
"""

import csv
import os

import pytest

from datetime import timedelta

from dia_alpha_monitor import (
    alerts,
    config_loader,
    defillama,
    dia_api,
    evm_oracle,
    feed_activity,
    grants as grant_analysis,
    reporting,
    scoring,
)
from dia_alpha_monitor.cli import main
from dia_alpha_monitor.db import Database
from dia_alpha_monitor.models import TvlSnapshot, today_str, utcnow


def test_db_snapshot_roundtrip(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.insert("market_snapshots", {
        "date": today_str(), "ts": utcnow().isoformat(),
        "price": 0.2, "market_cap": 40_000_000, "volume_24h": 4_000_000,
        "circulating_supply": 200_000_000, "total_supply": 200_000_000,
        "fdv": 40_000_000, "change_1d": 1.0, "change_7d": 2.0, "change_30d": 3.0,
        "source": "test", "stale": 0,
    })
    row = db.latest("market_snapshots")
    assert row["price"] == 0.2
    db.close()


def test_compute_proxy_weights():
    snaps = [
        TvlSnapshot(today_str(), utcnow().isoformat(), "a", "A", tvl=100, confidence="high"),
        TvlSnapshot(today_str(), utcnow().isoformat(), "b", "B", tvl=100, confidence="medium"),
        TvlSnapshot(today_str(), utcnow().isoformat(), "c", "C", tvl=100, confidence="low"),
        TvlSnapshot(today_str(), utcnow().isoformat(), "d", "D", tvl=None, confidence="high"),
    ]
    proxy = defillama.compute_proxy(snaps)
    assert proxy["gross_tvl"] == 300
    # 100*1.0 + 100*0.5 + 100*0.2 = 170
    assert proxy["confidence_weighted_tvl"] == 170
    assert proxy["n_resolved"] == 3
    assert proxy["n_protocols"] == 4


def test_chain_kind_uses_chain_endpoint(monkeypatch):
    """`kind: chain` entries read the latest point of the chain TVL series."""
    calls = {}

    def fake_get_json(url, **kwargs):
        calls["url"] = url
        return [{"date": 1, "tvl": 100.0}, {"date": 2, "tvl": 250.5}], None

    monkeypatch.setattr(defillama, "get_json", fake_get_json)
    snap = defillama.fetch_protocol_tvl(
        {"name": "Plume (ecosystem)", "slug": "Plume Mainnet", "kind": "chain"}
    )
    assert "/v2/historicalChainTvl/Plume Mainnet" in calls["url"]
    assert snap.tvl == 250.5  # latest point, not the first
    assert snap.error == ""


def test_protocol_kind_uses_protocol_endpoint(monkeypatch):
    """Default (no kind) entries still hit /protocol/{slug}."""
    calls = {}

    def fake_get_json(url, **kwargs):
        calls["url"] = url
        return {"currentChainTvls": {"Ethereum": 10.0, "Ethereum-staking": 5.0}}, None

    monkeypatch.setattr(defillama, "get_json", fake_get_json)
    snap = defillama.fetch_protocol_tvl({"name": "Euler", "slug": "euler"})
    assert "/protocol/euler" in calls["url"]
    assert snap.tvl == 10.0  # -staking suffix excluded from headline


def test_tvl_report_dedupes_per_slug_on_rerun(tmp_path):
    """Re-running the same day must not duplicate protocol rows in the report."""
    db = Database(str(tmp_path / "d.db"))
    date = today_str()
    db.insert("tvl_proxy", {
        "date": date, "ts": utcnow().isoformat(), "gross_tvl": 200,
        "confidence_weighted_tvl": 40, "n_protocols": 1, "n_resolved": 1,
    })
    # two runs on the same day write two rows for the same slug
    for tvl in (100.0, 150.0):
        db.insert("tvl_snapshots", {
            "date": date, "ts": utcnow().isoformat(), "slug": "morpho",
            "name": "Morpho", "tvl": tvl, "chain_tvls_json": "{}",
            "dia_role": "unknown", "confidence": "low", "source": "t", "error": "",
        })
    block = reporting.tvl_block(db)
    rows = block["protocols"]
    assert len(rows) == 1  # deduped to one row per slug
    assert rows[0]["tvl"] == 150.0  # newest snapshot wins
    db.close()


def _fake_dia_api(monkeypatch, quote=None, quote_err="", assets=None, exchanges=None):
    """Install a fake dia_api.get_json that dispatches on the endpoint."""
    def fake_get_json(url, **kwargs):
        if "assetQuotation" in url:
            return (None, quote_err) if quote_err else (quote, "")
        if "quotedAssets" in url:
            return assets, "" if assets is not None else "no data"
        if "exchanges" in url:
            return exchanges, "" if exchanges is not None else "no data"
        return None, "unexpected url"
    monkeypatch.setattr(dia_api, "get_json", fake_get_json)


def test_dia_api_parses_quotation_and_coverage(monkeypatch):
    _fake_dia_api(
        monkeypatch,
        quote={"Price": 0.125, "PriceYesterday": 0.130,
               "VolumeYesterdayUSD": 207000.0, "Signature": "0xabc"},
        assets=[{"x": 1}] * 5932,
        exchanges=[{"ScraperActive": True}, {"ScraperActive": True},
                   {"ScraperActive": False}],
    )
    snap = dia_api.fetch_dia_oracle()
    assert snap.dia_price == 0.125
    assert snap.dia_price_yesterday == 0.130
    assert snap.signature == "0xabc"
    assert snap.quoted_assets == 5932
    assert snap.exchange_sources == 3
    assert snap.active_scrapers == 2  # only ScraperActive truthy entries
    assert snap.error == ""


def test_dia_api_partial_failure_is_graceful(monkeypatch):
    # Quotation endpoint fails; coverage still resolves -> partial, no raise.
    _fake_dia_api(monkeypatch, quote_err="HTTP 500", assets=[{}] * 10, exchanges=[{"ScraperActive": True}])
    snap = dia_api.fetch_dia_oracle()
    assert snap.dia_price is None
    assert "quotation" in snap.error
    assert snap.quoted_assets == 10
    assert snap.active_scrapers == 1


def test_price_divergence_pct():
    assert dia_api.price_divergence_pct(0.10, 0.11) == pytest.approx(10.0)
    assert dia_api.price_divergence_pct(0.10, 0.09) == pytest.approx(-10.0)
    assert dia_api.price_divergence_pct(None, 0.10) is None
    assert dia_api.price_divergence_pct(0.10, None) is None
    assert dia_api.price_divergence_pct(0.0, 0.10) is None


def test_feed_activity_classifies_rwa_vs_crypto():
    assets = [
        {"Asset": {"Blockchain": "Ethereum"}},
        {"Asset": {"Blockchain": "Base"}},
        {"Asset": {"Blockchain": "Fiat"}},      # RWA marker
        {"Asset": {"Blockchain": "Stocks"}},    # RWA marker
    ]
    c = feed_activity.classify_assets(assets)
    assert c["total_feeds"] == 4
    assert c["rwa_feeds"] == 2
    assert c["crypto_feeds"] == 2
    assert c["n_blockchains"] == 4


def test_evm_oracle_counts_logs(monkeypatch):
    def fake_post(url, payload, **kwargs):
        if payload["method"] == "eth_blockNumber":
            return {"result": hex(100)}, ""
        if payload["method"] == "eth_getLogs":
            return {"result": [{}, {}, {}]}, ""  # 3 update logs
        return {"result": None}, ""

    monkeypatch.setattr(evm_oracle, "post_json", fake_post)
    snap = evm_oracle.poll_oracle(
        {"name": "X", "rpc_url": "http://x", "oracle_address": "0xabc", "lookback_blocks": 50}
    )
    assert snap.update_count == 3
    assert snap.latest_block == 100
    assert snap.from_block == 50 and snap.to_block == 100
    assert snap.error == ""


def test_evm_oracle_shrinks_window_on_range_error(monkeypatch):
    calls = {"getLogs": 0}

    def fake_post(url, payload, **kwargs):
        if payload["method"] == "eth_blockNumber":
            return {"result": hex(10000)}, ""
        if payload["method"] == "eth_getLogs":
            calls["getLogs"] += 1
            if calls["getLogs"] == 1:
                return {"error": {"message": "block range is too wide (maximum 1024)"}}, ""
            return {"result": [{}]}, ""
        return {"result": None}, ""

    monkeypatch.setattr(evm_oracle, "post_json", fake_post)
    snap = evm_oracle.poll_oracle(
        {"name": "Astar", "rpc_url": "http://a", "oracle_address": "0xabc", "lookback_blocks": 2000}
    )
    assert calls["getLogs"] == 2          # retried once with a smaller window
    assert snap.update_count == 1
    assert snap.from_block == 10000 - 1000  # window halved


def test_evm_oracle_missing_config_is_graceful():
    snap = evm_oracle.poll_oracle({"name": "Y"})  # no rpc/address
    assert snap.update_count is None
    assert "not configured" in snap.error


def test_grant_funnel_rates_and_stale():
    now = utcnow()
    old = (now - timedelta(days=200)).strftime("%Y-%m-%d")
    recent = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    grants = [
        {"project": "A", "chain": "X", "status": "mainnet", "date_added": old},
        {"project": "B", "chain": "Y", "status": "testnet", "date_added": old},     # stale
        {"project": "C", "chain": "Z", "status": "announced", "date_added": recent},  # not stale
        {"project": "D", "chain": "W", "status": "inactive", "date_added": old},
    ]
    f = grant_analysis.grant_funnel(grants, stale_days=90, now=now)
    assert f["counts"] == {"announced": 1, "testnet": 1, "mainnet": 1, "inactive": 1}
    assert f["to_mainnet_rate"] == 0.25            # 1/4 live
    assert f["to_testnet_rate"] == 0.5             # testnet+mainnet = 2/4
    assert f["n_stale"] == 1                        # only B (testnet, 200d old)
    assert f["stale"][0]["project"] == "B"


def test_tvl_growth_insufficient_history():
    # With < 7 days of history, trend must read INSUFFICIENT DATA, not a score.
    r = scoring.score_tvl_growth(0.0, 0.0, n_resolved=8, history_days=2)
    assert r.get("insufficient") is True
    assert "INSUFFICIENT DATA" in r["rationale"]
    # With enough history, it scores normally.
    r2 = scoring.score_tvl_growth(10.0, 20.0, n_resolved=8, history_days=14)
    assert not r2.get("insufficient")


def _insert_market(db, date, price):
    db.insert("market_snapshots", {
        "date": date, "ts": utcnow().isoformat(), "price": price,
        "market_cap": 1, "volume_24h": 1, "circulating_supply": 1,
        "total_supply": 1, "fdv": 1, "change_1d": 0, "change_7d": 0,
        "change_30d": 0, "source": "t", "stale": 0,
    })


def test_alerts_fire_on_big_wow_move(tmp_path):
    db = Database(str(tmp_path / "a.db"))
    eight_ago = (utcnow() - timedelta(days=8)).strftime("%Y-%m-%d")
    _insert_market(db, eight_ago, 0.10)
    _insert_market(db, today_str(), 0.13)   # +30% WoW
    fired = alerts.week_over_week_alerts(db, threshold=10.0)
    db.close()
    metrics = {a["metric"]: a for a in fired}
    assert "DIA price" in metrics
    assert metrics["DIA price"]["direction"] == "up"
    assert metrics["DIA price"]["pct"] > 10


def test_alerts_suppressed_without_history(tmp_path):
    db = Database(str(tmp_path / "b.db"))
    _insert_market(db, today_str(), 0.10)   # single day -> span 0
    fired = alerts.week_over_week_alerts(db, threshold=10.0)
    db.close()
    assert fired == []


def test_config_loaders_return_lists():
    # Uses the repo's config/ dir; should parse without raising.
    protocols, _ = config_loader.load_protocols()
    competitors, _ = config_loader.load_competitors()
    grants, _ = config_loader.load_grants()
    news, _ = config_loader.load_news()
    staking, _ = config_loader.load_staking()
    assert isinstance(protocols, list) and len(protocols) >= 1
    assert isinstance(competitors, list) and len(competitors) >= 1
    assert isinstance(grants, list)
    assert isinstance(news, list)
    assert isinstance(staking, list)


def test_grants_metrics():
    grants = [
        {"chain": "X", "status": "mainnet", "RWA": True, "date_added": "2999-01-01"},
        {"chain": "Y", "status": "announced", "RWA": False, "date_added": "2000-01-01"},
    ]
    m = config_loader.grants_metrics(grants)
    assert m["total"] == 2
    assert m["mainnet"] == 1
    assert m["rwa"] == 1
    assert m["n_chains"] == 2


def test_missing_config_is_graceful(monkeypatch, tmp_path):
    monkeypatch.setenv("DIA_CONFIG_DIR", str(tmp_path))  # empty dir
    # reload module-level CONFIG_DIR
    import importlib
    from dia_alpha_monitor import config_loader as cl
    importlib.reload(cl)
    items, warn = cl.load_protocols()
    assert items == []
    assert "missing" in warn
    importlib.reload(cl)  # restore default for other tests


def test_export_command_writes_csvs(tmp_path):
    db_path = str(tmp_path / "e.db")
    db = Database(db_path)
    db.insert("market_snapshots", {
        "date": today_str(), "ts": utcnow().isoformat(), "price": 0.2,
        "market_cap": 1, "volume_24h": 1, "circulating_supply": 1,
        "total_supply": 1, "fdv": 1, "change_1d": 0, "change_7d": 0,
        "change_30d": 0, "source": "t", "stale": 0,
    })
    db.close()
    out = str(tmp_path / "exports")
    rc = main(["--db", db_path, "export", "--out", out])
    assert rc == 0
    path = os.path.join(out, "market_snapshots.csv")
    assert os.path.exists(path)
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    assert rows and rows[0]["price"] == "0.2"
