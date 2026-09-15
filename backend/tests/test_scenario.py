import random

import pytest

from app import config
from app.scenario import allocate, build_plans, honest_ratio


def test_honest_ratio_descends_then_holds_at_floor():
    assert honest_ratio(1) == pytest.approx(0.60)
    assert honest_ratio(2) == pytest.approx(0.50)
    assert honest_ratio(3) == pytest.approx(0.40)
    assert honest_ratio(4) == pytest.approx(0.30)
    assert honest_ratio(9) == pytest.approx(0.30)


def test_round_one_allocation_is_twelve_five_three():
    assert allocate(20, 1) == {"honest": 12, "exaggerated": 5, "reversed": 3}


def test_allocation_always_sums_to_total():
    for round_no in range(1, 8):
        for total in (5, 12, 20, 33):
            counts = allocate(total, round_no)
            assert sum(counts.values()) == total


def test_non_honest_share_splits_five_to_three():
    counts = allocate(20, 3)          # 정직 8, 나머지 12
    assert counts["honest"] == 8
    assert counts["exaggerated"] == 8   # round(12 * 5/8) == 8 (7.5 -> 8)
    assert counts["reversed"] == 4


def test_reversed_impact_opposes_its_surface_tone():
    plans = build_plans(60, 1, random.Random(1), first_news_id=0, first_tick=0)
    reversed_plans = [p for p in plans if p.kind == "reversed"]
    assert reversed_plans, "역방향 뉴스가 생성되지 않았다"
    for p in reversed_plans:
        if p.surface_tone == "positive":
            assert p.impact < 0
        else:
            assert p.impact > 0


def test_honest_impact_agrees_with_its_surface_tone():
    plans = build_plans(60, 1, random.Random(2), first_news_id=0, first_tick=0)
    for p in (p for p in plans if p.kind == "honest"):
        assert (p.impact > 0) == (p.surface_tone == "positive")


def test_exaggerated_impact_is_negligible():
    plans = build_plans(60, 1, random.Random(3), first_news_id=0, first_tick=0)
    exaggerated = [p for p in plans if p.kind == "exaggerated"]
    assert exaggerated
    for p in exaggerated:
        assert abs(p.impact) <= config.IMPACT_RANGES["exaggerated"][1]


def test_same_seed_produces_identical_table():
    a = build_plans(20, 1, random.Random(7), first_news_id=0, first_tick=0)
    b = build_plans(20, 1, random.Random(7), first_news_id=0, first_tick=0)
    assert a == b


def test_publish_ticks_are_increasing_and_within_interval_range():
    plans = build_plans(20, 1, random.Random(11), first_news_id=0, first_tick=100)
    lo, hi = config.NEWS_INTERVAL_RANGE
    ticks = [p.publish_tick for p in plans]
    assert ticks == sorted(ticks)
    assert lo <= ticks[0] - 100 <= hi
    for earlier, later in zip(ticks, ticks[1:]):
        assert lo <= later - earlier <= hi


def test_news_ids_are_sequential_from_the_given_start():
    plans = build_plans(4, 1, random.Random(5), first_news_id=17, first_tick=0)
    assert [p.news_id for p in plans] == [17, 18, 19, 20]


def test_every_plan_names_a_real_stock_and_valid_ramp():
    plans = build_plans(40, 1, random.Random(13), first_news_id=0, first_tick=0)
    lo, hi = config.RAMP_SECONDS_RANGE
    for p in plans:
        assert p.symbol in config.STOCKS
        assert lo <= p.ramp_seconds <= hi
        assert p.surface_tone in ("positive", "negative")
        assert p.kind in ("honest", "exaggerated", "reversed")


def test_impact_range_constants_and_lookup_table_agree():
    assert config.IMPACT_RANGES == {
        "honest": config.IMPACT_HONEST,
        "exaggerated": config.IMPACT_EXAGGERATED,
        "reversed": config.IMPACT_REVERSED,
    }


def test_later_batches_get_more_traps():
    """라운드가 사라져도 난이도 곡선은 남는다 — 이제 뉴스 배치가 단계다."""
    assert honest_ratio(1) > honest_ratio(2) > honest_ratio(3)
    assert honest_ratio(9) == config.HONEST_RATIO_FLOOR
