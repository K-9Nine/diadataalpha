"""Integration-ish tests for config loading, DB, proxy and CLI export.

These avoid the network: they exercise the pure/local paths only.
"""

import csv
import os

import pytest

from datetime import timedelta

from dia_alpha_monitor import (
    alerts,
    coingecko,
    config_loader,
    defillama,
    dia_api,
    evm_oracle,
    feed_activity,
    grants as grant_analysis,
    lasernet,
    reporting,
    rss_ingest,
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


def test_lasernet_parses_string_counters(monkeypatch):
    # Blockscout returns big numbers as strings — must coerce to int.
    monkeypatch.setattr(
        lasernet, "get_json",
        lambda *a, **k: (
            {"total_transactions": "57441909", "transactions_today": "313152",
             "total_blocks": "28663051", "total_addresses": "2019"}, ""),
    )
    snap = lasernet.fetch_lasernet()
    assert snap.transactions_today == 313152
    assert snap.total_transactions == 57441909
    assert snap.total_blocks == 28663051
    assert snap.error == ""


def test_lasernet_graceful_on_failure(monkeypatch):
    monkeypatch.setattr(lasernet, "get_json", lambda *a, **k: (None, "HTTP 503"))
    snap = lasernet.fetch_lasernet()
    assert snap.transactions_today is None
    assert snap.error == "HTTP 503"


def test_feeds_meta_loads():
    meta, warn = config_loader.load_feeds_meta()
    assert isinstance(meta, dict)
    assert meta.get("rwa_assets_reported")  # shipped figure present


_SAMPLE_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>DIA Powers Fair Value Pricing for hemiBTC</title>
<link>https://www.diadata.org/blog/post/x</link>
<pubDate>Thu, 11 Jun 2026 14:50:03 +0000</pubDate></item>
<item><title>Update on DIA Staking</title>
<link>https://www.diadata.org/blog/post/y</link>
<pubDate>Fri, 05 Jun 2026 10:37:02 +0000</pubDate></item>
</channel></rss>"""


def test_rss_parse_and_classify():
    items = rss_ingest.parse_rss(_SAMPLE_RSS, source="DIA blog", default_impact=3)
    assert len(items) == 2
    assert items[0]["date"] == "2026-06-11"
    assert items[0]["category"] in ("integration", "RWA")  # "Powers ... Pricing"
    staking = items[1]
    assert staking["category"] == "staking"
    assert 1 <= staking["impact_score"] <= 5


def test_rss_ingest_dedups(monkeypatch, tmp_path):
    monkeypatch.setattr(rss_ingest, "get_text", lambda *a, **k: (_SAMPLE_RSS, ""))
    db = Database(str(tmp_path / "n.db"))
    feeds = [{"name": "DIA blog", "url": "http://x", "default_impact": 3}]
    r1 = rss_ingest.ingest(feeds, db)
    assert r1["new"] == 2 and r1["seen"] == 2
    r2 = rss_ingest.ingest(feeds, db)          # same items -> nothing new
    assert r2["new"] == 0 and r2["seen"] == 2
    assert len(rss_ingest.load_ingested(db)) == 2
    db.close()


def test_merged_news_manual_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(rss_ingest, "get_text", lambda *a, **k: (_SAMPLE_RSS, ""))
    db = Database(str(tmp_path / "m.db"))
    rss_ingest.ingest([{"name": "DIA blog", "url": "http://x", "default_impact": 3}], db)
    # Manual entry shares URL with ingested item 'x' (trailing slash) -> dedup.
    config_news = [{
        "url": "https://www.diadata.org/blog/post/x/", "title": "manual x",
        "category": "RWA", "impact_score": 5,
    }]
    merged = reporting.merged_news(db, config_news)
    urls = sorted(reporting._norm_url(n["url"]) for n in merged)
    assert urls == ["https://www.diadata.org/blog/post/x",
                    "https://www.diadata.org/blog/post/y"]   # x not duplicated
    x = [n for n in merged if reporting._norm_url(n["url"]).endswith("/x")][0]
    assert x["title"] == "manual x" and not x.get("ingested")  # manual won
    db.close()


def test_market_chart_buckets_to_daily(monkeypatch):
    # Two UTC days of points; the last point of each day should win.
    payload = {
        "prices": [[1700000000000, 1.0], [1700003600000, 1.1], [1700086400000, 2.0]],
        "market_caps": [[1700000000000, 10.0], [1700086400000, 20.0]],
        "total_volumes": [[1700000000000, 5.0]],
    }
    monkeypatch.setattr(coingecko, "get_json", lambda *a, **k: (payload, ""))
    rows, err = coingecko.fetch_market_chart("dia-data", days=2)
    assert err == "" and len(rows) == 2          # collapsed hourly -> 2 daily rows
    assert rows[0]["price"] == 1.1               # last point of day 1 wins
    assert rows[0]["market_cap"] == 10.0 and rows[0]["volume"] == 5.0
    assert rows[1]["price"] == 2.0 and rows[1]["volume"] is None


def test_lasernet_history_parse(monkeypatch):
    monkeypatch.setattr(
        lasernet, "get_json",
        lambda *a, **k: ({"chart": [
            {"date": "2026-06-12", "transactions_count": 313152},
            {"date": "2026-06-11", "transactions_count": "314559"},  # string coerced
        ]}, ""),
    )
    rows, err = lasernet.fetch_lasernet_history()
    assert err == "" and len(rows) == 2
    assert rows[0]["transactions_count"] == 313152
    assert rows[1]["transactions_count"] == 314559


def test_db_upsert_and_latest_value(tmp_path):
    db = Database(str(tmp_path / "h.db"))
    db.upsert("lasernet_history", {"date": "2026-06-10", "transactions_count": 100})
    db.upsert("lasernet_history", {"date": "2026-06-10", "transactions_count": 150})  # replace
    db.upsert("lasernet_history", {"date": "2026-06-12", "transactions_count": 200})
    n = db.conn.execute("SELECT COUNT(*) c FROM lasernet_history").fetchone()["c"]
    assert n == 2  # same-date row replaced, not duplicated
    assert db.latest_value("lasernet_history", "transactions_count") == 200  # newest date
    db.close()


def test_lasernet_block_trend_from_history(tmp_path):
    db = Database(str(tmp_path / "lt.db"))
    db.insert("lasernet_snapshots", {
        "date": today_str(), "ts": utcnow().isoformat(), "total_transactions": 57_000_000,
        "transactions_today": 320, "total_blocks": 28_000_000, "total_addresses": 2000,
        "source": "t", "error": "",
    })
    # 31 days of history: 30d ago = 200, 7d ago = 300, today = 330
    for ago, count in ((30, 200), (7, 300), (0, 330)):
        d = (utcnow() - timedelta(days=ago)).strftime("%Y-%m-%d")
        db.upsert("lasernet_history", {"date": d, "transactions_count": count})
    block = reporting.lasernet_block(db)
    assert block["wow_today"] == pytest.approx((330 - 300) / 300 * 100)   # +10%
    assert block["monthly"] == pytest.approx((330 - 200) / 200 * 100)     # +65%
    db.close()


def test_oracle_tvs_loads():
    meta, warn = config_loader.load_oracle_tvs()
    assert isinstance(meta, dict)
    assert meta.get("defillama_tvs_usd")  # shipped official-TVS figure present


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
