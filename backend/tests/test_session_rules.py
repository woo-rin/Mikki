import math
import random

import pytest

from app import config, engine, fundamentals, participants
from app.models import NewsPlan
from app.session import (
    TradeError,
    advance_round,
    ai_rows,
    buy,
    equity,
    goal_reached,
    grind_payout,
    is_bankrupt,
    is_locked,
    lock_remaining,
    max_affordable,
    new_session,
    prune_volume,
    record_fill,
    settle_grind,
    spend_analysis,
    spend_company_analysis,
    start_grind,
    volume_avg_of,
    volume_of,
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
    """주식을 들고 있으면 팔 수 있으니 파산이 아니다.

    수량을 고정하지 않는다 — 분기가 판마다 달라 시작가가 바뀐다.
    """
    sess = fresh()
    buy(sess, "geno", max_affordable(sess, "geno") // 2, now=0.0)
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


def test_grind_works_without_bankruptcy():
    """평소에도 열려 있다. 보수 감쇠와 120초 잠금이 스스로 균형을 잡는다 —
    부자일 때는 놓치는 램프가 잠금값보다 비싸다."""
    sess = fresh()
    info = start_grind(sess, now=0.0)
    assert info["payout"] == grind_payout(0)
    assert sess.grind_count == 1


def test_grind_extracts_at_most_half_the_seed_per_round():
    """상시로 열어도 라운드 목표(3배)에는 노가다만으로 못 닿는다."""
    total = sum(grind_payout(i) for i in range(40))
    assert total < config.SEED_CASH
    assert total < config.SEED_CASH * config.TARGET_MULTIPLIER


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
    start_grind(sess, now=200.0)         # 잠금이 풀렸으니 바로 다음 회차로 간다
    assert sess.cash == 200_000          # 1회차 보수는 사라지지 않고 지급됐다
    assert sess.grind_count == 2


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


def test_advance_round_does_not_move_prices():
    sess = fresh()
    before = {s: engine.price_of(sess.prices, s) for s in config.STOCKS}
    sess.cash = sess.target

    advance_round(sess)

    assert {s: engine.price_of(sess.prices, s) for s in config.STOCKS} == before


# ------------------------------------------------------- 체결 피드와 AI

def test_new_session_seats_the_default_count():
    sess = fresh()
    assert len(sess.ais) == config.AI_COUNT_DEFAULT
    assert len(sess.trades) == 0
    assert sess.trade_seq == 0


def test_record_fill_numbers_trades_from_one():
    sess = fresh()
    record_fill(sess, 10, "you", {"side": "buy", "symbol": "geno", "qty": 3,
                                  "price": 40_000, "value": 120_000})
    assert sess.trades[0]["seq"] == 1
    assert sess.trades[0]["actor"] == "you"
    assert sess.trades[0]["name"] == config.STOCKS["geno"].name
    assert sess.trades[0]["tick"] == 10


def test_recorded_trades_never_carry_value():
    """value 는 가격 영향 계산용 내부 값이다. 밖으로 나가면 안 된다."""
    sess = fresh()
    record_fill(sess, 1, "you", {"side": "buy", "symbol": "geno", "qty": 3,
                                 "price": 40_000, "value": 120_000})
    assert "value" not in sess.trades[0]


def test_volume_window_drops_old_fills():
    sess = fresh()
    record_fill(sess, 1, "you", {"side": "buy", "symbol": "geno",
                                 "qty": 10, "price": 1, "value": 10})
    record_fill(sess, 90, "you", {"side": "buy", "symbol": "geno",
                                  "qty": 5, "price": 1, "value": 5})
    prune_volume(sess, 90)
    assert volume_of(sess, "geno") == 5


def test_volume_counts_both_sides():
    sess = fresh()
    record_fill(sess, 1, "you", {"side": "buy", "symbol": "geno",
                                 "qty": 10, "price": 1, "value": 10})
    record_fill(sess, 2, "kim", {"side": "sell", "symbol": "geno",
                                 "qty": 4, "price": 1, "value": -4})
    assert volume_of(sess, "geno") == 14


def test_volume_avg_is_zero_before_any_trade():
    assert volume_avg_of(fresh(), "geno", tick=300) == 0


def test_ai_rows_rank_by_equity_descending():
    sess = fresh()
    for index, ai in enumerate(sess.ais):
        ai.cash = 1_000_000 + index * 10_000
    rows = ai_rows(sess)
    assert [r["rank"] for r in rows] == list(range(1, len(sess.ais) + 1))
    assert rows[0]["cash"] > rows[-1]["cash"]


def test_ai_rows_break_ties_by_roster_order():
    """임의로 흔들리면 리더보드가 매 폴링마다 요동친다."""
    sess = fresh()
    for ai in sess.ais:
        ai.cash = 1_000_000
    first = [r["id"] for r in ai_rows(sess)]
    assert first == [r["id"] for r in ai_rows(sess)]
    assert first == [a.profile.id for a in sess.ais]


def test_ai_rows_never_expose_holdings():
    for row in ai_rows(fresh()):
        assert set(row) == {"id", "name", "cash", "equity", "rank"}


# ------------------------------------------------------- AI 의 tick 구동

def _drive(sess, plans, ticks, seed=7):
    """AI 를 ticks 까지 굴리고 tick 별 순주문액을 모은다."""
    flows = []
    for tick in range(1, ticks + 1):
        flows.append(participants.run_tick(
            sess.ais, plans, tick, seed,
            lambda s: 40_000,
            lambda actor, fill, t=tick: record_fill(sess, t, actor, fill),
        ))
    return flows


def test_ai_reacts_exactly_at_its_reaction_tick():
    sess = fresh()
    sess.ais = participants.new_participants(1)          # 정소장, 반응 3t
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=5)

    flows = _drive(sess, [p], 12)

    assert [tick for tick, flow in enumerate(flows, start=1) if flow] == [8]


def test_ai_reacts_to_each_news_only_once():
    sess = fresh()
    sess.ais = participants.new_participants(1)
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=0)

    _drive(sess, [p], 40)
    assert len([t for t in sess.trades if t["side"] == "buy"]) == 1


def test_a_fooled_ai_buys_into_a_reversed_trap():
    sess = fresh()
    sess.ais = participants.new_participants(9)
    trap = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                    kind="reversed", impact=-0.10, ramp_seconds=20,
                    publish_tick=0)

    _drive(sess, [trap], 20)
    buyers = {t["actor"] for t in sess.trades if t["side"] == "buy"}
    assert buyers, "아무도 안 낚이면 함정이 성립하지 않는다"
    assert len(buyers) < 9, "전원이 낚이면 신원을 읽을 수 없다"


def test_flow_value_sign_matches_the_side():
    sess = fresh()
    sess.ais = participants.new_participants(1)
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=0)
    assert any(flow.get("geno", 0) > 0 for flow in _drive(sess, [p], 6))


def test_same_seed_replays_the_same_trades():
    """재현이 안 되면 밸런스를 못 고친다."""
    def run():
        sess = new_session("s", random.Random(0), started_at=0.0)
        p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                     kind="reversed", impact=-0.10, ramp_seconds=20,
                     publish_tick=0)
        _drive(sess, [p], 20, seed=4242)
        return [(t["actor"], t["side"], t["qty"]) for t in sess.trades]

    assert run() == run()


def test_ai_driven_incremental_matches_bulk():
    """**이 작업에서 가장 깨지기 쉬운 성질이다.**

    탭을 비웠다 돌아온 요청(일괄)과 500ms 폴링(증분)이 같은 가격·같은
    체결을 내야 한다. AI 판단이 engine 의 rng 를 소비하면 여기서 깨진다.
    """
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=3)

    def make():
        sess = new_session("s", random.Random(0), started_at=0.0)
        sess.plans.append(p)
        return sess

    def driver_for(sess):
        def run(at):
            return participants.run_tick(
                sess.ais, sess.plans, at, sess.ai_seed,
                lambda sym: engine.price_of(sess.prices, sym),
                lambda actor, fill, t=at: record_fill(sess, t, actor, fill),
            )
        return run

    stepwise = make()
    rng = random.Random(77)
    driver = driver_for(stepwise)
    for tick in range(1, 61):
        engine.advance(stepwise.prices, stepwise.plans, tick, rng, on_tick=driver)

    at_once = make()
    engine.advance(at_once.prices, at_once.plans, 60, random.Random(77),
                   on_tick=driver_for(at_once))

    assert stepwise.prices.log_return == at_once.prices.log_return
    assert stepwise.prices.flow_log == at_once.prices.flow_log
    assert [(t["seq"], t["actor"], t["side"], t["qty"]) for t in stepwise.trades] \
        == [(t["seq"], t["actor"], t["side"], t["qty"]) for t in at_once.trades]


# ------------------------------------------------------------ 체결 상한

def test_trade_feed_has_a_ceiling():
    """상한이 없으면 1시간에 2,400건까지 쌓여 세션 하나가 1MB 를 넘는다."""
    sess = fresh()
    for tick in range(config.TRADES_MAX + 200):
        record_fill(sess, tick, "kim", {"side": "buy", "symbol": "geno",
                                        "qty": 1, "price": 1, "value": 1})
    assert len(sess.trades) == config.TRADES_MAX


def test_trade_feed_keeps_the_newest():
    sess = fresh()
    for tick in range(config.TRADES_MAX + 10):
        record_fill(sess, tick, "kim", {"side": "buy", "symbol": "geno",
                                        "qty": 1, "price": 1, "value": 1})
    seqs = [t["seq"] for t in sess.trades]
    assert seqs[-1] == config.TRADES_MAX + 10
    assert seqs == sorted(seqs)


# ------------------------------------------------------------ 분기 선택

def test_each_game_picks_a_quarter():
    sess = fresh()
    assert 0 <= sess.quarter_index < fundamentals.quarter_count()


def test_the_same_seed_picks_the_same_quarter():
    a = new_session("a", random.Random(9), started_at=0.0)
    b = new_session("b", random.Random(9), started_at=0.0)
    assert a.quarter_index == b.quarter_index


def test_quarters_differ_between_games():
    """펀더멘털 다양성이 판 사이로 옮겨왔다."""
    picks = {new_session("s", random.Random(s), 0.0).quarter_index for s in range(40)}
    assert len(picks) > 1


def test_prices_start_from_the_picked_quarter():
    sess = new_session("s", random.Random(3), started_at=0.0)
    expected = fundamentals.fair_values(sess.quarter_index)
    for symbol in config.STOCKS:
        implied = sess.prices.start_price[symbol] * math.exp(
            sess.prices.anchor_log[symbol]
        )
        assert implied == pytest.approx(expected[symbol], rel=1e-9)


# ------------------------------------------------------------ 현금 목표

def test_goal_counts_cash_only():
    """목표는 '레이스를 얼마나 달렸나' 다. 팔아서 확정한 것만 센다."""
    sess = fresh()
    sess.cash = sess.target
    assert goal_reached(sess) is True


def test_holding_stock_worth_the_target_is_not_enough():
    """사서 오르기만 해서는 못 이긴다. 이것이 매도에 의미를 준다."""
    sess = fresh()
    price = engine.price_of(sess.prices, "geno")
    sess.holdings["geno"] = sess.target // price + 1
    sess.cash = 0

    assert equity(sess) >= sess.target
    assert goal_reached(sess) is False


def test_bankruptcy_still_counts_holdings():
    """잣대를 통일하지 않는다 — 파산은 '아직 할 수 있나' 다."""
    sess = fresh()
    price = engine.price_of(sess.prices, "geno")
    sess.holdings["geno"] = 500_000 // price
    sess.cash = 0

    assert sess.cash < config.BANKRUPTCY_THRESHOLD
    assert is_bankrupt(sess) is False


def test_target_is_three_times_the_seed_and_fixed():
    sess = fresh()
    assert sess.target == config.SEED_CASH * config.TARGET_MULTIPLIER
    sess.cash = 9_000_000
    assert sess.target == config.SEED_CASH * config.TARGET_MULTIPLIER
