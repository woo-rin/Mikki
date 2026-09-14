import math
import random

import pytest

from app import config, engine, fundamentals
from app.session import (
    TradeError,
    advance_round,
    buy,
    equity,
    goal_reached,
    grind_payout,
    is_bankrupt,
    is_locked,
    lock_remaining,
    new_session,
    settle_grind,
    spend_analysis,
    spend_company_analysis,
    start_grind,
)


def fresh():
    return new_session("s1", random.Random(0), started_at=0.0)


def broke(cash=50_000):
    sess = fresh()
    sess.cash = cash
    sess.holdings = {}
    return sess


# ---------------------------------------------------------------- 파산 판정

def test_not_bankrupt_at_seed():
    assert is_bankrupt(fresh()) is False


def test_bankrupt_below_threshold():
    assert is_bankrupt(broke(config.BANKRUPTCY_THRESHOLD - 1)) is True


def test_not_bankrupt_exactly_at_threshold():
    assert is_bankrupt(broke(config.BANKRUPTCY_THRESHOLD)) is False


def test_holdings_count_toward_solvency():
    """주식을 들고 있으면 팔 수 있으니 파산이 아니다."""
    sess = fresh()
    buy(sess, "geno", 20, now=0.0)
    sess.cash = 0
    assert is_bankrupt(sess) is False


def test_trading_still_allowed_while_bankrupt():
    """노가다는 막힌 길이 아니라 추가로 생기는 선택지다."""
    sess = broke(50_000)
    buy(sess, "taesan", 1, now=0.0)
    assert sess.holdings["taesan"] == 1


# ---------------------------------------------------------------- 노가다

def test_grind_payout_decays_by_round():
    assert grind_payout(0) == 200_000
    assert grind_payout(1) == 120_000
    assert grind_payout(2) == 72_000
    assert grind_payout(3) == 43_200


def test_grind_payout_keeps_decaying_and_never_goes_negative():
    payouts = [grind_payout(n) for n in range(0, 14)]
    assert payouts[:5] == [200_000, 120_000, 72_000, 43_200, 25_920]
    for earlier, later in zip(payouts, payouts[1:]):
        assert later < earlier
    assert payouts[-1] >= 0


def test_start_grind_locks_for_the_configured_duration():
    sess = broke()
    info = start_grind(sess, now=1000.0)
    assert info["payout"] == 200_000
    assert info["unlock_at"] == 1000.0 + config.GRIND_LOCK_SECONDS
    assert is_locked(sess, now=1000.0) is True
    assert is_locked(sess, now=1000.0 + config.GRIND_LOCK_SECONDS - 1) is True
    assert is_locked(sess, now=1000.0 + config.GRIND_LOCK_SECONDS) is False


def test_grind_pays_nothing_until_the_lock_expires():
    sess = broke(50_000)
    start_grind(sess, now=0.0)
    assert settle_grind(sess, now=60.0) == 0
    assert sess.cash == 50_000
    assert settle_grind(sess, now=config.GRIND_LOCK_SECONDS) == 200_000
    assert sess.cash == 250_000


def test_grind_settles_only_once():
    sess = broke(50_000)
    start_grind(sess, now=0.0)
    settle_grind(sess, now=200.0)
    assert settle_grind(sess, now=300.0) == 0
    assert sess.cash == 250_000


def test_second_grind_pays_less():
    sess = broke(0)
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    sess.cash = 0
    start_grind(sess, now=1000.0)
    settle_grind(sess, now=1000.0 + config.GRIND_LOCK_SECONDS)
    assert sess.cash == 120_000


def test_grind_requires_bankruptcy():
    with pytest.raises(TradeError) as excinfo:
        start_grind(fresh(), now=0.0)
    assert excinfo.value.code == "not_bankrupt"


def test_grind_cannot_be_started_while_already_locked():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        start_grind(sess, now=10.0)
    assert excinfo.value.code == "locked"


def test_lock_remaining_counts_down():
    sess = broke()
    start_grind(sess, now=500.0)
    assert lock_remaining(sess, now=500.0) == config.GRIND_LOCK_SECONDS
    assert lock_remaining(sess, now=560.0) == config.GRIND_LOCK_SECONDS - 60
    assert lock_remaining(sess, now=9999.0) == 0


def test_trading_is_blocked_while_grinding():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "taesan", 1, now=30.0)
    assert excinfo.value.code == "locked"


def test_trading_resumes_after_the_lock():
    sess = broke()
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    buy(sess, "taesan", 1, now=config.GRIND_LOCK_SECONDS)
    assert sess.holdings["taesan"] == 1


def test_expired_grind_settles_before_a_new_one_can_start():
    """잠금이 자연히 풀린 뒤 정산 없이 재시작하면 1회차 보수가 사라졌다."""
    sess = broke(0)
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        start_grind(sess, now=200.0)
    assert excinfo.value.code == "not_bankrupt"
    assert sess.cash == 200_000          # 1회차 보수는 사라지지 않고 지급됐다


def test_no_payout_is_lost_when_grinding_again_while_still_bankrupt():
    """보수가 파산선을 넘기지 못하는 회차에서는 연속 노가다가 가능하고, 어느 회차도 사라지지 않는다."""
    sess = broke(0)
    sess.grind_count = 4                 # 5회차 보수 25,920 — 파산선을 넘기지 못한다
    start_grind(sess, now=0.0)
    start_grind(sess, now=200.0)         # 정산 없이 재시작
    assert sess.cash == 25_920           # 5회차 보수가 자동 정산됐다
    settle_grind(sess, now=320.0)
    assert sess.cash == 25_920 + 15_552  # 6회차 보수까지 정상 지급


# ---------------------------------------------------------------- 분석 차감

def test_analysis_budget_runs_out_after_five():
    sess = fresh()
    for _ in range(config.ANALYSES_PER_ROUND):
        spend_analysis(sess, now=0.0)
    assert sess.analyses_left == 0
    with pytest.raises(TradeError) as excinfo:
        spend_analysis(sess, now=0.0)
    assert excinfo.value.code == "no_analyses_left"


def test_analysis_is_blocked_while_grinding():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        spend_analysis(sess, now=5.0)
    assert excinfo.value.code == "locked"


# ---------------------------------------------------------------- 라운드

def test_goal_not_reached_at_seed():
    assert goal_reached(fresh()) is False


def test_goal_reached_at_target():
    sess = fresh()
    sess.cash = sess.target
    assert goal_reached(sess) is True


def test_advance_round_triples_the_target_and_refills():
    sess = fresh()
    sess.cash = 3_000_000
    sess.analyses_left = 0
    sess.grind_count = 2

    advance_round(sess)

    assert sess.round_no == 2
    assert sess.round_start_equity == 3_000_000
    assert sess.target == 9_000_000
    assert sess.analyses_left == config.ANALYSES_PER_ROUND
    assert sess.grind_count == 0


def test_grind_payout_resets_with_the_round():
    """라운드가 넘어가면 노가다 회차가 초기화되어 다시 20만부터다."""
    sess = fresh()
    sess.grind_count = 3
    sess.cash = sess.target
    advance_round(sess)
    sess.cash = 0
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    assert sess.cash == 200_000


# ------------------------------------------------------------ 기업분석

def test_company_analysis_starts_at_the_configured_count():
    assert fresh().company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND


def test_spending_a_company_analysis_decrements_and_records():
    sess = fresh()
    charged = spend_company_analysis(sess, "geno", now=0.0)
    assert charged is True
    assert sess.company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND - 1
    assert "geno" in sess.analyzed_symbols


def test_reanalyzing_the_same_symbol_is_free():
    """재무는 라운드 내내 안 바뀐다. 같은 값을 두 번 팔면 함정이다."""
    sess = fresh()
    spend_company_analysis(sess, "geno", now=0.0)
    left = sess.company_analyses_left

    charged = spend_company_analysis(sess, "geno", now=0.0)
    assert charged is False
    assert sess.company_analyses_left == left


def test_company_analysis_runs_out():
    sess = fresh()
    for symbol in list(config.STOCKS)[: config.COMPANY_ANALYSES_PER_ROUND]:
        spend_company_analysis(sess, symbol, now=0.0)

    remaining = [s for s in config.STOCKS if s not in sess.analyzed_symbols][0]
    with pytest.raises(TradeError) as caught:
        spend_company_analysis(sess, remaining, now=0.0)
    assert caught.value.code == "no_company_analyses_left"


def test_company_analysis_rejects_unknown_symbol():
    with pytest.raises(TradeError) as caught:
        spend_company_analysis(fresh(), "nope", now=0.0)
    assert caught.value.code == "unknown_symbol"


def test_company_analysis_is_blocked_while_grinding():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as caught:
        spend_company_analysis(sess, "geno", now=1.0)
    assert caught.value.code == "locked"


def test_advance_round_refills_company_analyses_and_clears_symbols():
    sess = fresh()
    spend_company_analysis(sess, "geno", now=0.0)
    sess.cash = sess.target

    advance_round(sess)

    assert sess.company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND
    assert sess.analyzed_symbols == set()


def test_advance_round_reanchors_to_the_new_quarter():
    """라운드 2 는 2분기 실적을 본다. 적정가가 움직여야 한다."""
    sess = fresh()
    before = dict(sess.prices.anchor_log)
    sess.cash = sess.target

    advance_round(sess)

    assert sess.prices.anchor_log != before
    expected = fundamentals.fair_values(2)
    for symbol in config.STOCKS:
        implied = sess.prices.start_price[symbol] * math.exp(
            sess.prices.anchor_log[symbol]
        )
        assert implied == pytest.approx(expected[symbol], rel=1e-9)


def test_advance_round_does_not_move_prices():
    sess = fresh()
    before = {s: engine.price_of(sess.prices, s) for s in config.STOCKS}
    sess.cash = sess.target

    advance_round(sess)

    assert {s: engine.price_of(sess.prices, s) for s in config.STOCKS} == before
