import math
import random

import pytest

from app import config, engine, fundamentals
from app.engine import (
    advance,
    new_state,
    price_of,
    ramp_progress,
    ramp_remaining,
)
from app.models import NewsPlan


class ZeroRandom(random.Random):
    """노이즈를 죽여 램프만 남긴다."""

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return 0.0


@pytest.fixture
def no_anchor(monkeypatch):
    """앵커를 끄고 램프만 남긴다.

    아래 여섯 테스트는 램프의 산술을 정확한 값으로 단정한다. 앵커가 함께
    돌면 그 값이 흔들려 무엇을 재는 테스트인지 흐려진다. 두 축이 함께
    움직이는 것은 test_anchor_* 가 따로 본다.
    """
    monkeypatch.setattr(config, "ANCHOR_PULL", 0.0)


def _state(rng: random.Random | None = None):
    """테스트용 기본 상태. 오프셋 난수를 고정해 결정론을 유지한다."""
    return new_state(fundamentals.fair_values(1), rng or random.Random(12345))


def plan(symbol="geno", impact=0.10, ramp=20, publish_tick=0, news_id=0):
    return NewsPlan(
        news_id=news_id,
        symbol=symbol,
        surface_tone="positive" if impact > 0 else "negative",
        kind="honest",
        impact=impact,
        ramp_seconds=ramp,
        publish_tick=publish_tick,
    )


def test_no_news_and_no_noise_leaves_price_untouched(no_anchor):
    state = _state()
    advance(state, [], to_tick=500, rng=ZeroRandom(0))
    for symbol in config.STOCKS:
        assert price_of(state, symbol) == state.start_price[symbol]


def test_price_at_ramp_end_equals_base_times_exp_impact(no_anchor):
    state = _state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    expected = math.floor(state.start_price["geno"] * math.exp(0.10))
    assert price_of(state, "geno") == expected


def test_ramp_stops_contributing_after_it_finishes(no_anchor):
    state = _state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    at_end = price_of(state, "geno")
    advance(state, [p], to_tick=400, rng=ZeroRandom(0))
    assert price_of(state, "geno") == at_end


def test_price_midway_through_ramp_is_half_the_impact(no_anchor):
    state = _state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=10, rng=ZeroRandom(0))
    expected = math.floor(state.start_price["geno"] * math.exp(0.05))
    assert price_of(state, "geno") == expected


def test_negative_impact_pushes_price_down(no_anchor):
    state = _state()
    p = plan(impact=-0.08, ramp=16, publish_tick=0)
    advance(state, [p], to_tick=16, rng=ZeroRandom(0))
    assert price_of(state, "geno") < state.start_price["geno"]


def test_news_only_moves_its_own_symbol(no_anchor):
    state = _state()
    p = plan(symbol="geno", impact=0.12, ramp=15, publish_tick=0)
    advance(state, [p], to_tick=15, rng=ZeroRandom(0))
    for symbol in config.STOCKS:
        if symbol != "geno":
            assert price_of(state, symbol) == state.start_price[symbol]


def test_incremental_advance_matches_one_big_advance():
    """500ms 폴링이든 탭을 비웠다 돌아오든 같은 가격이 나와야 한다."""
    plans = [plan(impact=0.09, ramp=25, publish_tick=30, news_id=1)]

    stepwise = _state()
    rng_a = random.Random(42)
    for tick in range(1, 101):
        advance(stepwise, plans, to_tick=tick, rng=rng_a)

    at_once = _state()
    advance(at_once, plans, to_tick=100, rng=random.Random(42))

    assert stepwise.log_return == at_once.log_return
    assert stepwise.last_tick == at_once.last_tick == 100


def test_advance_ignores_plans_whose_ramp_already_resolved():
    """끝난 램프를 계속 넘겨도 결과가 같아야 한다 — 필터가 가격을 바꾸지 않는다는 보장."""
    resolved = plan(impact=0.10, ramp=20, publish_tick=0, news_id=0)

    with_resolved = _state()
    advance(with_resolved, [resolved], to_tick=20, rng=ZeroRandom(0))
    advance(with_resolved, [resolved], to_tick=200, rng=ZeroRandom(0))

    without = _state()
    advance(without, [resolved], to_tick=20, rng=ZeroRandom(0))
    advance(without, [], to_tick=200, rng=ZeroRandom(0))

    assert with_resolved.log_return == without.log_return


def test_advance_to_a_past_tick_is_a_no_op():
    state = _state()
    advance(state, [], to_tick=50, rng=random.Random(1))
    snapshot = dict(state.log_return)
    advance(state, [], to_tick=20, rng=random.Random(1))
    assert state.log_return == snapshot
    assert state.last_tick == 50


def test_noise_actually_moves_prices():
    state = _state()
    advance(state, [], to_tick=200, rng=random.Random(3))
    assert any(
        price_of(state, symbol) != state.start_price[symbol]
        for symbol in config.STOCKS
    )


def test_ramp_progress_clamps_to_zero_and_one():
    p = plan(impact=0.10, ramp=20, publish_tick=100)
    assert ramp_progress(p, 90) == pytest.approx(0.0)
    assert ramp_progress(p, 100) == pytest.approx(0.0)
    assert ramp_progress(p, 110) == pytest.approx(0.5)
    assert ramp_progress(p, 120) == pytest.approx(1.0)
    assert ramp_progress(p, 999) == pytest.approx(1.0)


def test_ramp_remaining_counts_down_to_zero():
    p = plan(impact=0.10, ramp=20, publish_tick=100)
    assert ramp_remaining(p, 100) == 20
    assert ramp_remaining(p, 112) == 8
    assert ramp_remaining(p, 120) == 0
    assert ramp_remaining(p, 500) == 0


def test_start_prices_survive_the_float_round_trip():
    """log(base) 를 저장하면 exp 왕복에서 1원이 사라진다 — 6종목 중 4종목이 그랬다.
    누적 로그수익을 저장하고 정수 시작가에 곱해야 tick 0 가 정확하다."""
    state = _state()
    for symbol in config.STOCKS:
        assert price_of(state, symbol) == state.start_price[symbol]


def test_start_price_lands_within_the_offset_band():
    fair = fundamentals.fair_values(1)
    state = _state()
    lo, hi = config.START_OFFSET_RANGE
    for symbol in config.STOCKS:
        ratio = state.start_price[symbol] / fair[symbol]
        assert 1 + lo <= ratio <= 1 + hi


def test_start_offset_is_deterministic_for_a_seed():
    """같은 시드는 같은 판을 만든다. 재현 없이는 밸런스를 못 고친다."""
    fair = fundamentals.fair_values(1)
    first = new_state(fair, random.Random(7))
    second = new_state(fair, random.Random(7))
    assert first.start_price == second.start_price
    assert first.anchor_log == second.anchor_log


def test_start_offset_differs_between_seeds():
    """매판 어느 종목이 고평가인지 달라져야 기업분석이 살아있다."""
    fair = fundamentals.fair_values(1)
    seeds = [new_state(fair, random.Random(seed)).start_price for seed in range(8)]
    assert len({tuple(sorted(s.items())) for s in seeds}) > 1


def test_anchor_log_points_at_the_fair_value():
    fair = fundamentals.fair_values(1)
    state = new_state(fair, random.Random(7))
    for symbol in config.STOCKS:
        implied = state.start_price[symbol] * math.exp(state.anchor_log[symbol])
        assert implied == pytest.approx(fair[symbol], rel=1e-9)


def test_reanchor_moves_the_anchor_but_not_the_price():
    """라운드 전환에 가격이 점프하면 보유 종목 평가액이 순간이동한다."""
    state = _state()
    advance(state, [], to_tick=50, rng=random.Random(3))
    before = {symbol: price_of(state, symbol) for symbol in config.STOCKS}
    before_anchor = dict(state.anchor_log)

    engine.reanchor(state, fundamentals.fair_values(2))

    assert {symbol: price_of(state, symbol) for symbol in config.STOCKS} == before
    assert state.anchor_log != before_anchor


def _flat_state(fair=10_000, start=13_000):
    """전 종목을 같은 적정가·시작가에 세운다. 앵커만 따로 관찰하기 위한 것이다."""
    fair_values = {symbol: fair for symbol in config.STOCKS}
    state = new_state(fair_values, random.Random(1))
    state.start_price = {symbol: start for symbol in config.STOCKS}
    engine.reanchor(state, fair_values)
    return state, fair


def test_anchor_pulls_an_overvalued_stock_down():
    state, fair = _flat_state(start=13_000)
    before = price_of(state, "geno")
    advance(state, [], to_tick=60, rng=ZeroRandom(0))
    after = price_of(state, "geno")

    assert after < before
    assert after > fair      # 한 번에 도달하지는 않는다


def test_anchor_pushes_an_undervalued_stock_up():
    state, fair = _flat_state(start=7_000)
    before = price_of(state, "geno")
    advance(state, [], to_tick=60, rng=ZeroRandom(0))
    after = price_of(state, "geno")

    assert after > before
    assert after < fair


def test_anchor_converges_on_the_fair_value():
    """충분히 오래 두면 적정가에 닿는다."""
    state, fair = _flat_state(start=13_000)
    advance(state, [], to_tick=5_000, rng=ZeroRandom(0))
    assert price_of(state, "geno") == pytest.approx(fair, rel=0.001)


def test_anchor_never_overshoots():
    """평균회귀는 목표를 지나치지 않는다. 지나치면 진동한다."""
    state, fair = _flat_state(start=13_000)
    for tick in range(1, 400):
        advance(state, [], to_tick=tick, rng=ZeroRandom(0))
        assert price_of(state, "geno") >= fair


def test_anchor_pulls_back_after_a_ramp_ends():
    """호재가 진짜여도 램프가 끝나면 앵커가 되돌린다. 두 축이 싸운다."""
    state, fair = _flat_state(start=10_000)
    p = plan(impact=0.20, ramp=20, publish_tick=0)

    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    peak = price_of(state, "geno")
    assert peak > fair

    advance(state, [p], to_tick=400, rng=ZeroRandom(0))
    assert price_of(state, "geno") < peak


def test_anchor_is_weaker_than_a_news_ramp():
    """앵커가 뉴스를 이기면 AI 분석 5회의 희소성이 무너진다."""
    state, fair = _flat_state(start=10_000)
    p = plan(impact=0.10, ramp=30, publish_tick=0)
    advance(state, [p], to_tick=30, rng=ZeroRandom(0))
    assert price_of(state, "geno") > fair


def test_anchor_keeps_incremental_and_bulk_identical():
    """앵커는 난수를 쓰지 않는다. 기존 불변식이 유지돼야 한다."""
    fair = fundamentals.fair_values(1)
    stepwise = new_state(fair, random.Random(7))
    rng = random.Random(99)
    for tick in range(1, 41):
        advance(stepwise, [], to_tick=tick, rng=rng)

    at_once = new_state(fair, random.Random(7))
    advance(at_once, [], to_tick=40, rng=random.Random(99))

    assert stepwise.log_return == at_once.log_return


# ------------------------------------------------------------ 가격 이력

def test_history_records_one_price_per_tick():
    state = _state()
    advance(state, [], to_tick=10, rng=random.Random(2))
    assert len(engine.history_of(state, "geno")) == 10


def test_history_is_capped_at_the_window():
    """따라잡기로 1,800 tick 이 돌아도 메모리는 고정이어야 한다."""
    state = _state()
    advance(state, [], to_tick=500, rng=random.Random(2))
    for symbol in config.STOCKS:
        assert len(engine.history_of(state, symbol)) == config.PRICE_HISTORY_TICKS


def test_history_last_entry_is_the_current_price():
    state = _state()
    advance(state, [], to_tick=30, rng=random.Random(2))
    for symbol in config.STOCKS:
        assert engine.history_of(state, symbol)[-1] == price_of(state, symbol)


def test_history_is_empty_before_the_first_tick():
    assert engine.history_of(_state(), "geno") == []


def test_incremental_and_bulk_produce_the_same_history():
    """새로고침한 사람과 계속 보던 사람이 같은 차트를 봐야 한다."""
    stepwise = _state()
    rng = random.Random(9)
    for tick in range(1, 101):
        advance(stepwise, [], to_tick=tick, rng=rng)

    at_once = _state()
    advance(at_once, [], to_tick=100, rng=random.Random(9))

    for symbol in config.STOCKS:
        assert engine.history_of(stepwise, symbol) == engine.history_of(at_once, symbol)


def test_history_follows_a_news_ramp(no_anchor):
    """차트가 실제 가격을 따라가야 한다 — 램프 구간에서 단조 증가."""
    state = _state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    series = engine.history_of(state, "geno")
    assert series == sorted(series)
    assert series[-1] > series[0]
