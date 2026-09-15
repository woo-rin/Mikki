"""AI 참가자. 명단, 판단, 매매를 소유한다.

engine 은 이 파일을 모른다 — "이 tick 에 얼마어치 순매수" 만 콜백으로 받는다.

난수는 engine 의 rng 를 쓰지 않는다. AI 가 매매한 tick 과 안 한 tick 의 난수
소비량이 달라지면 증분 계산과 일괄 계산이 어긋나고, 그 불변식이 이 서버에서
가장 중요한 성질이다. 대신 (시드, AI 번호, 기사 번호) 로 그때그때 뽑는다 —
tick 진행 순서와 무관하게 같은 값이 나온다.
"""
import math
import random
from dataclasses import dataclass, field

from app import config
from app.models import NewsPlan


@dataclass
class AIState:
    profile: config.AI
    cash: int
    # symbol -> (수량, 누적 매입원가). 익절 판정에 평단이 필요하다.
    holdings: dict[str, tuple[int, int]] = field(default_factory=dict)
    # plans 안에서 아직 반응하지 않은 첫 위치. 매 tick 전체를 훑으면
    # 따라잡기 비용이 기사 수 × AI 수 × tick 수로 커진다.
    cursor: int = 0


def new_participants(count: int) -> list[AIState]:
    """명단 위에서 count 명. 기본 5면 고수 2 와 중간 3 이라 초보 난이도다."""
    return [
        AIState(profile=profile, cash=config.SEED_CASH)
        for profile in config.AI_ROSTER[:count]
    ]


def sees_through(
    ai_seed: int, ai_index: int, profile: config.AI, news_id: int
) -> bool:
    """이 AI 가 이 기사의 낚시를 꿰뚫어 보는가. 호출 순서와 무관하다."""
    roll = random.Random(
        (ai_seed * 1_000_003) ^ (news_id * 31) ^ (ai_index * 7)
    ).random()
    return roll < profile.insight


def view_of(plan: NewsPlan, sees: bool) -> str:
    """'bullish' | 'bearish'.

    꿰뚫어 보면 실제 임팩트의 **부호만** 본다. 크기까지 알면 고수 AI 가 완벽해져
    플레이어가 따라잡을 수 없다. 못 보면 표면 톤을 그대로 믿는다 — 역방향 함정이
    성립하는 지점이다.
    """
    if sees:
        return "bullish" if plan.impact > 0 else "bearish"
    return "bullish" if plan.surface_tone == "positive" else "bearish"


def _fee(gross: int) -> int:
    return math.floor(gross * config.TRADE_FEE_RATE)


def buy(ai: AIState, symbol: str, price: int) -> dict | None:
    """현금의 bet_ratio 만큼 산다. 한 주도 못 사면 None.

    플레이어와 같은 규칙이다 — 양방향 0.2% 수수료, 같은 가격.
    """
    budget = math.floor(ai.cash * ai.profile.bet_ratio)
    qty = budget // price
    while qty > 0 and price * qty + _fee(price * qty) > ai.cash:
        qty -= 1
    if qty <= 0:
        return None

    gross = price * qty
    fee = _fee(gross)
    ai.cash -= gross + fee
    held_qty, held_cost = ai.holdings.get(symbol, (0, 0))
    # 원가에 수수료를 포함한다. 빼면 익절선이 실제보다 일찍 걸린다.
    ai.holdings[symbol] = (held_qty + qty, held_cost + gross + fee)
    return {"side": "buy", "symbol": symbol, "qty": qty,
            "price": price, "value": gross}


def sell_all(ai: AIState, symbol: str, price: int) -> dict | None:
    """공매도가 없으므로 파는 것은 언제나 전량이다."""
    held = ai.holdings.get(symbol)
    if held is None or held[0] <= 0:
        return None

    qty = held[0]
    gross = price * qty
    ai.cash += gross - _fee(gross)
    del ai.holdings[symbol]
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "value": -gross}


def should_take_profit(ai: AIState, symbol: str, price: int) -> bool:
    """평가액이 매입원가의 (1 + 익절선) 을 넘었는가."""
    held = ai.holdings.get(symbol)
    if held is None or held[0] <= 0:
        return False
    qty, cost = held
    return price * qty >= cost * (1.0 + ai.profile.take_profit)


def equity_of(ai: AIState, price_of) -> int:
    """현금 + 보유 평가액. price_of 는 symbol 을 받아 정수 가격을 돌려준다."""
    return ai.cash + sum(
        price_of(symbol) * qty for symbol, (qty, _) in ai.holdings.items()
    )
