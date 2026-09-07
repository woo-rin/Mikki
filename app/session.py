"""세션 상태와 도메인 규칙. Claude 도 HTTP 도 모른다.

시각은 언제나 now 인자로 받는다 — 그래야 120초 잠금을 sleep 없이 테스트한다.
"""
import math
import random
from dataclasses import dataclass, field

from app import config, engine
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
    plans: list[NewsPlan] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)


def new_session(session_id: str, rng: random.Random, started_at: float) -> GameSession:
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        prices=engine.new_state(),
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
