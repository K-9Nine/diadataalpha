"""Unit tests for the alpha-scoring model."""

from dia_alpha_monitor import scoring


def test_total_max_is_100():
    assert scoring.TOTAL_MAX == 100


def test_category_points_never_exceed_max():
    res = scoring.score_momentum(1000, 1000, 1.0)  # absurdly high inputs
    assert res["points"] <= res["max"] == 15


def test_momentum_missing_data_is_neutral_and_flagged():
    res = scoring.score_momentum(None, None, None)
    assert res["gap"] is True
    assert res["points"] == round(15 * scoring.NEUTRAL_FRACTION, 2)


def test_momentum_directionality():
    strong = scoring.score_momentum(20, 30, 0.10)
    weak = scoring.score_momentum(-20, -30, 0.0)
    assert strong["points"] > weak["points"]
    assert weak["points"] == 0


def test_tvl_growth_neutral_when_history_missing_but_tvl_present():
    res = scoring.score_tvl_growth(None, None, n_resolved=3)
    assert res["gap"] is True
    assert "no prior history" in res["rationale"]


def test_tvl_growth_rewards_growth():
    up = scoring.score_tvl_growth(15, 30, 3)
    down = scoring.score_tvl_growth(-15, -30, 3)
    assert up["points"] > down["points"]
    assert up["points"] <= 25


def test_grants_empty_is_neutral():
    res = scoring.score_grants(0, 0, 0)
    assert res["gap"] is True


def test_grants_scaling():
    res = scoring.score_grants(new_30d=4, mainnet=6, total=6)
    assert res["points"] == 15  # all sub-maxes hit


def test_rwa_scoring():
    res = scoring.score_rwa(rwa_grants=3, rwa_recent_news=3, rwa_total_news=5)
    assert res["points"] == 15
    gap = scoring.score_rwa(0, 0, 0)
    assert gap["gap"] is True


def test_staking_requires_latest():
    assert scoring.score_staking(None, None, None, has_latest=False)["gap"] is True
    one_snap = scoring.score_staking(None, None, None, has_latest=True)
    assert one_snap["gap"] is True


def test_staking_rewards_growth():
    res = scoring.score_staking(delta_staked=1_000_000, delta_feeders=2, delta_tx=50_000, has_latest=True)
    assert res["points"] == 15


def test_valuation_discount_more_discount_scores_higher():
    deep = scoring.score_valuation_discount(0.01)
    shallow = scoring.score_valuation_discount(0.10)
    assert deep["points"] > shallow["points"]
    assert scoring.score_valuation_discount(None)["gap"] is True


def test_aggregate():
    cats = [
        scoring.score_momentum(10, 10, 0.05),
        scoring.score_tvl_growth(10, 10, 3),
        scoring.score_grants(2, 3, 5),
        scoring.score_rwa(2, 1, 3),
        scoring.score_staking(100, 1, 100, True),
        scoring.score_valuation_discount(0.02),
    ]
    agg = scoring.aggregate(cats)
    assert agg["max"] == 100
    assert 0 <= agg["total"] <= 100
    assert len(agg["categories"]) == 6
