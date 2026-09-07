import math
import random

import pytest

from app import config
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


def test_no_news_and_no_noise_leaves_price_untouched():
    state = new_state()
    advance(state, [], to_tick=500, rng=ZeroRandom(0))
    for symbol, stock in config.STOCKS.items():
        assert price_of(state, symbol) == stock.base_price


def test_price_at_ramp_end_equals_base_times_exp_impact():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    expected = math.floor(config.STOCKS["geno"].base_price * math.exp(0.10))
    assert price_of(state, "geno") == expected


def test_ramp_stops_contributing_after_it_finishes():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    at_end = price_of(state, "geno")
    advance(state, [p], to_tick=400, rng=ZeroRandom(0))
    assert price_of(state, "geno") == at_end


def test_price_midway_through_ramp_is_half_the_impact():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=10, rng=ZeroRandom(0))
    expected = math.floor(config.STOCKS["geno"].base_price * math.exp(0.05))
    assert price_of(state, "geno") == expected


def test_negative_impact_pushes_price_down():
    state = new_state()
    p = plan(impact=-0.08, ramp=16, publish_tick=0)
    advance(state, [p], to_tick=16, rng=ZeroRandom(0))
    assert price_of(state, "geno") < config.STOCKS["geno"].base_price


def test_news_only_moves_its_own_symbol():
    state = new_state()
    p = plan(symbol="geno", impact=0.12, ramp=15, publish_tick=0)
    advance(state, [p], to_tick=15, rng=ZeroRandom(0))
    for symbol, stock in config.STOCKS.items():
        if symbol != "geno":
            assert price_of(state, symbol) == stock.base_price


def test_incremental_advance_matches_one_big_advance():
    """500ms 폴링이든 탭을 비웠다 돌아오든 같은 가격이 나와야 한다."""
    plans = [plan(impact=0.09, ramp=25, publish_tick=30, news_id=1)]

    stepwise = new_state()
    rng_a = random.Random(42)
    for tick in range(1, 101):
        advance(stepwise, plans, to_tick=tick, rng=rng_a)

    at_once = new_state()
    advance(at_once, plans, to_tick=100, rng=random.Random(42))

    assert stepwise.log_return == at_once.log_return
    assert stepwise.last_tick == at_once.last_tick == 100


def test_advance_to_a_past_tick_is_a_no_op():
    state = new_state()
    advance(state, [], to_tick=50, rng=random.Random(1))
    snapshot = dict(state.log_return)
    advance(state, [], to_tick=20, rng=random.Random(1))
    assert state.log_return == snapshot
    assert state.last_tick == 50


def test_noise_actually_moves_prices():
    state = new_state()
    advance(state, [], to_tick=200, rng=random.Random(3))
    assert any(
        price_of(state, symbol) != stock.base_price
        for symbol, stock in config.STOCKS.items()
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


def test_base_prices_survive_the_float_round_trip():
    """log(base) 를 저장하면 exp 왕복에서 1원이 사라진다 — 6종목 중 4종목이 그랬다.
    누적 로그수익을 저장하고 정수 시작가에 곱해야 tick 0 가 정확하다."""
    state = new_state()
    for symbol, stock in config.STOCKS.items():
        assert price_of(state, symbol) == stock.base_price
