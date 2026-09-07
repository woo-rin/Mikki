"""가격 엔진. 상태와 목표 tick 을 받아 로그가격을 증분으로 진행한다.

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
    last_tick: int = 0


def new_state() -> PriceState:
    # 로그가격이 아니라 누적 로그수익을 든다. log(base) 를 저장하면 exp 왕복에서
    # 1원이 사라진다(6종목 중 4종목). 정수 시작가는 정확히 남기고 수익률만 float 로 둔다.
    return PriceState(
        log_return={symbol: 0.0 for symbol in config.STOCKS},
        last_tick=0,
    )


def advance(
    state: PriceState,
    plans: Sequence[NewsPlan],
    to_tick: int,
    rng: random.Random,
) -> None:
    """state 를 to_tick 까지 진행한다. to_tick 이 과거면 아무것도 하지 않는다."""
    for tick in range(state.last_tick + 1, to_tick + 1):
        # 종목 순회 순서를 고정해야 증분 계산과 일괄 계산이 같은 난수를 소비한다.
        for symbol, stock in config.STOCKS.items():
            state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
        for plan in plans:
            if plan.publish_tick < tick <= plan.publish_tick + plan.ramp_seconds:
                state.log_return[plan.symbol] += plan.impact / plan.ramp_seconds
    state.last_tick = max(state.last_tick, to_tick)


def price_of(state: PriceState, symbol: str) -> int:
    """원 단위 정수. 내림으로 통일한다."""
    return math.floor(
        config.STOCKS[symbol].base_price * math.exp(state.log_return[symbol])
    )


def ramp_progress(plan: NewsPlan, tick: int) -> float:
    elapsed = tick - plan.publish_tick
    if elapsed <= 0:
        return 0.0
    return min(1.0, elapsed / plan.ramp_seconds)


def ramp_remaining(plan: NewsPlan, tick: int) -> int:
    ends_at = plan.publish_tick + plan.ramp_seconds
    return max(0, ends_at - tick)
