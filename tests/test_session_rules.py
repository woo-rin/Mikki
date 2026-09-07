import math
import random

import pytest

from app import config
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
