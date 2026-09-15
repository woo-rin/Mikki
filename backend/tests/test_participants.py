import random

import pytest

from app import config, participants
from app.models import NewsPlan


def plan(symbol="geno", impact=0.10, tone="positive", news_id=0, publish_tick=0):
    return NewsPlan(
        news_id=news_id, symbol=symbol, surface_tone=tone, kind="honest",
        impact=impact, ramp_seconds=20, publish_tick=publish_tick,
    )


def profile(insight=0.5, reaction=3, bet=0.3, take=0.15):
    return config.AI("test", "테스트", insight, reaction, bet, take)


# ------------------------------------------------------------------ 명단

def test_roster_has_nine():
    assert len(config.AI_ROSTER) == config.AI_COUNT_MAX == 9


def test_roster_ids_and_names_are_unique():
    assert len({a.id for a in config.AI_ROSTER}) == 9
    assert len({a.name for a in config.AI_ROSTER}) == 9


def test_roster_parameters_are_in_range():
    for ai in config.AI_ROSTER:
        assert 0.0 <= ai.insight <= 1.0
        assert ai.reaction_ticks >= 1
        assert 0.0 < ai.bet_ratio <= 1.0
        assert ai.take_profit > 0.0


def test_roster_rank_disagrees_with_insight():
    """통찰력 순서와 실력 순서가 어긋나야 '옳게 고르는 것과 이기는 것은 다르다'가 나온다."""
    by_insight = sorted(config.AI_ROSTER, key=lambda a: -a.insight)
    worst_discipline = max(config.AI_ROSTER, key=lambda a: a.take_profit)
    fastest = min(config.AI_ROSTER, key=lambda a: a.reaction_ticks)

    assert worst_discipline in by_insight[:3], "익절 못 하는 AI 가 통찰력 상위권에 있어야 한다"
    assert fastest in by_insight[-3:], "가장 빠른 AI 는 통찰력 하위권이어야 한다"


def test_new_participants_takes_the_top_n():
    five = participants.new_participants(5)
    assert [a.profile.id for a in five] == [a.id for a in config.AI_ROSTER[:5]]


def test_participants_start_with_seed_cash_and_nothing_held():
    for ai in participants.new_participants(9):
        assert ai.cash == config.SEED_CASH
        assert ai.holdings == {}
        assert ai.cursor == 0


# ------------------------------------------------------------ 통찰력 판정

def test_sees_through_is_deterministic():
    """같은 시드는 같은 판단을 낸다. 재현 없이는 밸런스를 못 고친다."""
    args = (12345, 2, profile(insight=0.5), 7)
    assert participants.sees_through(*args) == participants.sees_through(*args)


def test_sees_through_ignores_call_order():
    """tick 진행 순서와 무관해야 증분/일괄 동일성이 유지된다."""
    pairs = {(i, n): participants.sees_through(99, i, profile(), n)
             for i in range(3) for n in range(4)}
    for i in reversed(range(3)):
        for n in reversed(range(4)):
            assert participants.sees_through(99, i, profile(), n) == pairs[(i, n)]


def test_insight_one_always_sees_through():
    for news_id in range(50):
        assert participants.sees_through(7, 0, profile(insight=1.0), news_id)


def test_insight_zero_never_sees_through():
    for news_id in range(50):
        assert not participants.sees_through(7, 0, profile(insight=0.0), news_id)


def test_insight_roughly_matches_its_probability():
    hits = sum(participants.sees_through(3, 1, profile(insight=0.7), n)
               for n in range(2000))
    assert 0.65 < hits / 2000 < 0.75


def test_different_ais_disagree_on_the_same_news():
    """전원이 똑같이 판단하면 체결 피드에서 신원을 읽을 수 없다."""
    verdicts = {participants.sees_through(5, i, profile(insight=0.5), 42)
                for i in range(9)}
    assert len(verdicts) == 2


# -------------------------------------------------------------- 시각 판정

def test_seeing_through_follows_the_real_impact():
    assert participants.view_of(plan(impact=0.10), sees=True) == "bullish"
    assert participants.view_of(plan(impact=-0.10), sees=True) == "bearish"


def test_being_fooled_follows_the_surface_tone():
    """역방향 함정이 성립하는 지점이다 — 호재로 읽히는데 실제로는 내려간다."""
    trap = plan(impact=-0.10, tone="positive")
    assert participants.view_of(trap, sees=False) == "bullish"
    assert participants.view_of(trap, sees=True) == "bearish"


def test_exaggerated_news_fools_even_a_seer():
    """과장 기사는 부호가 표면과 같다. 통찰력이 높아도 약한 재료를 거르지 못한다.

    의도한 것이다 — 과장은 판별이 아니라 크기의 문제다.
    """
    weak = plan(impact=0.004, tone="positive")
    assert participants.view_of(weak, sees=True) == "bullish"
    assert participants.view_of(weak, sees=False) == "bullish"


# ------------------------------------------------------------------ 매매

def _ai(cash=config.SEED_CASH, **kwargs):
    return participants.AIState(profile=profile(**kwargs), cash=cash)


def test_buy_spends_the_bet_ratio_and_pays_the_fee():
    ai = _ai(bet=0.30)
    fill = participants.buy(ai, "geno", 40_000)

    assert fill["side"] == "buy" and fill["symbol"] == "geno"
    assert fill["qty"] == 7                      # 30만 // 4만
    assert fill["value"] == 7 * 40_000
    # 플레이어와 같은 규칙 — 양방향 0.2%
    assert ai.cash == config.SEED_CASH - 280_000 - 560


def test_buy_records_cost_including_fee():
    """평단에 수수료가 빠지면 익절선이 실제보다 일찍 걸린다."""
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    assert ai.holdings["geno"] == (7, 280_000 + 560)


def test_buying_twice_accumulates_quantity_and_cost():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    participants.buy(ai, "geno", 50_000)
    qty, cost = ai.holdings["geno"]
    assert qty > 7 and cost > 280_560


def test_buy_returns_none_when_it_cannot_afford_one_share():
    ai = _ai(cash=1_000, bet=0.30)
    assert participants.buy(ai, "geno", 40_000) is None
    assert ai.holdings == {}
    assert ai.cash == 1_000


def test_sell_all_clears_the_position_and_pays_the_fee():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    cash_after_buy = ai.cash

    fill = participants.sell_all(ai, "geno", 50_000)

    assert fill["side"] == "sell" and fill["qty"] == 7
    assert fill["value"] == -7 * 50_000
    assert "geno" not in ai.holdings
    assert ai.cash == cash_after_buy + 350_000 - 700


def test_sell_all_on_nothing_is_none():
    assert participants.sell_all(_ai(), "geno", 40_000) is None


def test_take_profit_triggers_above_the_line():
    ai = _ai(bet=0.30, take=0.15)
    participants.buy(ai, "geno", 40_000)
    assert participants.should_take_profit(ai, "geno", 44_000) is False   # +10%
    assert participants.should_take_profit(ai, "geno", 47_000) is True    # +17%


def test_take_profit_is_measured_against_cost_not_price():
    """수수료 때문에 매입원가는 체결가보다 높다. 평단 기준이어야 정확하다."""
    ai = _ai(bet=0.30, take=0.0001)
    participants.buy(ai, "geno", 40_000)
    assert participants.should_take_profit(ai, "geno", 40_000) is False


def test_take_profit_on_nothing_is_false():
    assert participants.should_take_profit(_ai(), "geno", 40_000) is False


def test_equity_counts_cash_and_holdings():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    assert participants.equity_of(ai, lambda s: 40_000) == ai.cash + 7 * 40_000


def test_a_broke_ai_simply_stops():
    """노가다는 플레이어 전용 구제 장치다. AI 는 조용히 멈춘다."""
    ai = _ai(cash=0, bet=0.50)
    assert participants.buy(ai, "geno", 40_000) is None
    assert not hasattr(participants, "start_grind")
