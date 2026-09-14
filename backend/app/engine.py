"""가격 엔진. 상태와 목표 tick 을 받아 누적 로그수익을 증분으로 진행한다.

백그라운드 타이머를 돌리지 않는다. 요청이 올 때 마지막 계산 tick 부터
현재 tick 까지만 이어서 계산하므로, 500ms 폴링이면 매 요청 0~1 tick 이고
탭을 비웠다 돌아오면 밀린 tick 을 한꺼번에 계산한다.
"""
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from app import config
from app.models import NewsPlan


@dataclass
class PriceState:
    log_return: dict[str, float] = field(default_factory=dict)
    start_price: dict[str, int] = field(default_factory=dict)
    anchor_log: dict[str, float] = field(default_factory=dict)
    last_tick: int = 0


def new_state(fair_values: dict[str, int], rng: random.Random) -> PriceState:
    """적정가 대비 랜덤 위치에서 출발한다.

    로그가격이 아니라 누적 로그수익을 든다. log(start) 를 저장하면 exp 왕복에서
    1원이 사라진다(6종목 중 4종목). 정수 시작가는 정확히 남기고 수익률만 float 로 둔다.
    """
    lo, hi = config.START_OFFSET_RANGE
    start_price: dict[str, int] = {}
    anchor_log: dict[str, float] = {}
    # 종목 순회 순서를 고정해야 같은 시드가 같은 판을 만든다.
    for symbol in config.STOCKS:
        fair = fair_values[symbol]
        start = max(1, math.floor(fair * (1.0 + rng.uniform(lo, hi))))
        start_price[symbol] = start
        anchor_log[symbol] = math.log(fair / start)
    return PriceState(
        log_return={symbol: 0.0 for symbol in config.STOCKS},
        start_price=start_price,
        anchor_log=anchor_log,
        last_tick=0,
    )


def reanchor(state: PriceState, fair_values: dict[str, int]) -> None:
    """적정가만 갱신한다. start_price 와 log_return 은 건드리지 않는다.

    가격이 점프하면 플레이어가 들고 있던 종목의 평가액이 순간이동한다.
    """
    for symbol, fair in fair_values.items():
        state.anchor_log[symbol] = math.log(fair / state.start_price[symbol])


def advance(
    state: PriceState,
    plans: Sequence[NewsPlan],
    to_tick: int,
    rng: random.Random,
) -> None:
    """state 를 to_tick 까지 진행한다. to_tick 이 과거면 아무것도 하지 않는다."""
    if to_tick <= state.last_tick:
        return

    # 이 구간에 기여할 수 있는 뉴스만 한 번 추린다. plans 는 보충마다 20건씩
    # 늘고 가지치기되지 않으므로, 램프가 이미 끝난 계획을 매 tick 다시 훑으면
    # 폴링 비용이 세션 길이에 비례해 커지고, 오래 자리를 비웠다 돌아온 요청이
    # 이벤트 루프를 붙잡아 다른 플레이어까지 멈춘다.
    # 난수는 종목 루프에서만 쓰이므로 이 필터는 가격을 바꾸지 않는다.
    active = [
        plan
        for plan in plans
        if plan.publish_tick < to_tick
        and plan.publish_tick + plan.ramp_seconds > state.last_tick
    ]

    for tick in range(state.last_tick + 1, to_tick + 1):
        # 종목 순회 순서를 고정해야 증분 계산과 일괄 계산이 같은 난수를 소비한다.
        for symbol, stock in config.STOCKS.items():
            state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
        for plan in active:
            if plan.publish_tick < tick <= plan.publish_tick + plan.ramp_seconds:
                state.log_return[plan.symbol] += plan.impact / plan.ramp_seconds
    state.last_tick = max(state.last_tick, to_tick)


def price_of(state: PriceState, symbol: str) -> int:
    """원 단위 정수. 내림으로 통일한다."""
    return math.floor(state.start_price[symbol] * math.exp(state.log_return[symbol]))


def ramp_progress(plan: NewsPlan, tick: int) -> float:
    elapsed = tick - plan.publish_tick
    if elapsed <= 0:
        return 0.0
    return min(1.0, elapsed / plan.ramp_seconds)


def ramp_remaining(plan: NewsPlan, tick: int) -> int:
    ends_at = plan.publish_tick + plan.ramp_seconds
    return max(0, ends_at - tick)
