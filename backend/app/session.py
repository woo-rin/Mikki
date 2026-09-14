"""세션 상태와 도메인 규칙. Claude 도 HTTP 도 모른다.

시각은 언제나 now 인자로 받는다 — 그래야 120초 잠금을 sleep 없이 테스트한다.
"""
import math
import random
from dataclasses import dataclass, field

from app import config, engine, fundamentals
from app.engine import PriceState
from app.models import NewsItem, NewsPlan


class TradeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GameSession:
    session_id: str
    rng: random.Random
    started_at: float
    prices: PriceState
    cash: int
    holdings: dict[str, int] = field(default_factory=dict)
    round_no: int = 1
    round_start_equity: int = config.SEED_CASH
    target: int = config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER
    analyses_left: int = config.ANALYSES_PER_ROUND
    grind_count: int = 0
    grind_until: float | None = None
    pending_payout: int = 0
    plans: list[NewsPlan] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)


def new_session(session_id: str, rng: random.Random, started_at: float) -> GameSession:
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        prices=engine.new_state(fundamentals.fair_values(1), rng),
        cash=config.SEED_CASH,
        round_start_equity=config.SEED_CASH,
        target=config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER,
    )


def equity(sess: GameSession) -> int:
    """현금 + 보유 평가액. 전부 내림한 정수."""
    valuation = sum(
        engine.price_of(sess.prices, symbol) * qty
        for symbol, qty in sess.holdings.items()
    )
    return sess.cash + valuation


def _fee(gross: int) -> int:
    return math.floor(gross * config.TRADE_FEE_RATE)


def _check_symbol(symbol: str) -> None:
    if symbol not in config.STOCKS:
        raise TradeError("unknown_symbol", f"없는 종목입니다: {symbol}")


def _check_qty(qty: int) -> None:
    if qty <= 0:
        raise TradeError("bad_quantity", "수량은 1주 이상이어야 합니다.")


def max_affordable(sess: GameSession, symbol: str) -> int:
    """수수료까지 감당할 수 있는 최대 수량."""
    _check_symbol(symbol)
    price = engine.price_of(sess.prices, symbol)
    qty = sess.cash // price
    while qty > 0 and price * qty + _fee(price * qty) > sess.cash:
        qty -= 1
    return qty


def buy(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_unlocked(sess, now)
    _check_symbol(symbol)
    _check_qty(qty)
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    if gross + fee > sess.cash:
        raise TradeError("insufficient_cash", "현금이 부족합니다.")
    sess.cash -= gross + fee
    sess.holdings[symbol] = sess.holdings.get(symbol, 0) + qty
    return {"side": "buy", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}


def sell(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_unlocked(sess, now)
    _check_symbol(symbol)
    _check_qty(qty)
    held = sess.holdings.get(symbol, 0)
    if qty > held:
        raise TradeError("insufficient_shares", "보유 수량이 부족합니다.")
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    sess.cash += gross - fee
    if held == qty:
        del sess.holdings[symbol]
    else:
        sess.holdings[symbol] = held - qty
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}


# ------------------------------------------------------- 파산과 노가다

def is_bankrupt(sess: GameSession) -> bool:
    return equity(sess) < config.BANKRUPTCY_THRESHOLD


def is_locked(sess: GameSession, now: float) -> bool:
    return sess.grind_until is not None and now < sess.grind_until


def lock_remaining(sess: GameSession, now: float) -> int:
    if sess.grind_until is None:
        return 0
    return max(0, math.ceil(sess.grind_until - now))


def _check_unlocked(sess: GameSession, now: float) -> None:
    if is_locked(sess, now):
        raise TradeError("locked", "노가다 중에는 조작할 수 없습니다.")


def grind_payout(grind_count: int) -> int:
    """회차마다 3/5 배로 줄어든다. 1회차가 grind_count == 0 이다.

    부동소수점으로 계산하면 4회차가 43,199 로 어긋나므로 정수 나눗셈을 쓴다.
    """
    return (
        config.GRIND_BASE_PAYOUT
        * config.GRIND_DECAY_NUM ** grind_count
        // config.GRIND_DECAY_DEN ** grind_count
    )


def start_grind(sess: GameSession, now: float) -> dict:
    # 이전 노가다의 미지급 보수를 먼저 정산한다. 잠금이 자연히 풀린 뒤 정산 없이
    # 다시 시작하면 pending_payout 이 덮어써져 미지급액이 영구히 사라진다.
    settle_grind(sess, now)
    _check_unlocked(sess, now)
    if not is_bankrupt(sess):
        raise TradeError("not_bankrupt", "파산 상태에서만 노가다를 할 수 있습니다.")
    payout = grind_payout(sess.grind_count)
    sess.grind_until = now + config.GRIND_LOCK_SECONDS
    sess.pending_payout = payout
    sess.grind_count += 1
    return {"payout": payout, "unlock_at": sess.grind_until}


def settle_grind(sess: GameSession, now: float) -> int:
    """잠금이 끝났으면 미지급 보수를 현금에 넣고 그 금액을 돌려준다."""
    if sess.pending_payout == 0 or is_locked(sess, now):
        return 0
    payout = sess.pending_payout
    sess.cash += payout
    sess.pending_payout = 0
    sess.grind_until = None
    return payout


# ------------------------------------------------------------ 분석 차감

def spend_analysis(sess: GameSession, now: float) -> None:
    _check_unlocked(sess, now)
    if sess.analyses_left <= 0:
        raise TradeError("no_analyses_left", "이 라운드의 분석 횟수를 다 썼습니다.")
    sess.analyses_left -= 1


# --------------------------------------------------------------- 라운드

def goal_reached(sess: GameSession) -> bool:
    return equity(sess) >= sess.target


def advance_round(sess: GameSession) -> None:
    current = equity(sess)
    sess.round_no += 1
    sess.round_start_equity = current
    sess.target = current * config.ROUND_TARGET_MULTIPLIER
    sess.analyses_left = config.ANALYSES_PER_ROUND
    sess.grind_count = 0
