"""세션 상태와 도메인 규칙. Claude 도 HTTP 도 모른다.

시각은 언제나 now 인자로 받는다 — 그래야 120초 잠금을 sleep 없이 테스트한다.
"""
import math
import random
from collections import deque
from dataclasses import dataclass, field

from app import config, engine, fundamentals, participants
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
    # 종목별 누적 매입원가(수수료 포함). holdings 의 모양은 건드리지 않는다 —
    # 읽는 곳이 여럿이라 파급이 크다.
    cost_basis: dict[str, int] = field(default_factory=dict)
    round_no: int = 1
    round_start_equity: int = config.SEED_CASH
    target: int = config.SEED_CASH * config.TARGET_MULTIPLIER
    analyses_left: int = config.ANALYSES_PER_ROUND
    company_analyses_left: int = config.COMPANY_ANALYSES_PER_ROUND
    analyzed_symbols: set[str] = field(default_factory=set)
    grind_count: int = 0
    grind_until: float | None = None
    pending_payout: int = 0
    ais: list[participants.AIState] = field(default_factory=list)
    ai_seed: int = 0
    # 판마다 다른 분기를 본다. 라운드가 사라지면서 펀더멘털 다양성이
    # 판 안에서 판 사이로 옮겨왔다.
    quarter_index: int = 0
    status: str = "running"            # "running" | "finished"
    winner: str | None = None          # "you" 또는 AI 이름
    ranking: list[dict] | None = None
    # 마지막으로 요청이 닿은 시각. 오래 조용하면 쓸려나간다.
    last_seen: float = 0.0
    trades: deque = field(default_factory=deque)
    trade_seq: int = 0
    # (tick, symbol, qty). 오래된 것은 prune_volume 이 버린다.
    volume_window: deque = field(default_factory=deque)
    volume_total: dict[str, int] = field(default_factory=dict)
    plans: list[NewsPlan] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)


def new_session(
    session_id: str,
    rng: random.Random,
    started_at: float,
    ai_count: int = config.AI_COUNT_DEFAULT,
) -> GameSession:
    quarter_index = rng.randrange(fundamentals.quarter_count())
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        quarter_index=quarter_index,
        prices=engine.new_state(fundamentals.fair_values(quarter_index), rng),
        cash=config.SEED_CASH,
        round_start_equity=config.SEED_CASH,
        target=config.SEED_CASH * config.TARGET_MULTIPLIER,
        last_seen=started_at,
        ais=participants.new_participants(ai_count),
        # AI 판단용 시드. engine 의 rng 와 섞지 않는다.
        ai_seed=rng.randrange(2**31),
        volume_total={symbol: 0 for symbol in config.STOCKS},
        trades=deque(maxlen=config.TRADES_MAX),
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
    # 수수료를 원가에 넣는다. 빼면 평가손익이 실제보다 좋아 보인다.
    sess.cost_basis[symbol] = sess.cost_basis.get(symbol, 0) + gross + fee
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
        sess.cost_basis.pop(symbol, None)
    else:
        sess.holdings[symbol] = held - qty
        # 판 만큼만 원가에서 덜어낸다. 남은 주식의 취득 단가는 그대로다.
        cost = sess.cost_basis.get(symbol, 0)
        sess.cost_basis[symbol] = cost - math.floor(cost * qty / held)
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}


def avg_cost_of(sess: GameSession, symbol: str) -> int | None:
    """취득 단가(수수료 포함), 내림. 안 들고 있으면 None.

    0 으로 채우지 않는다 — 프론트가 그걸 평단으로 믿고 틀린 손익을 그린다.
    """
    qty = sess.holdings.get(symbol, 0)
    if qty <= 0:
        return None
    return sess.cost_basis.get(symbol, 0) // qty


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
    # 파산이 전제가 아니다 — 평소에도 누를 수 있다.
    #
    # 보수가 3/5 씩 줄고 120초 동안 아무것도 못 하므로, 스스로 균형이 잡힌다.
    # 부자일 때는 그동안 놓치는 램프가 보수보다 비싸고, 가난할 때만 남는 장사다.
    # 전부 뽑아도 라운드당 약 50만원이라 목표(3배)에는 노가다만으로 못 닿는다.
    _check_unlocked(sess, now)
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


def spend_company_analysis(sess: GameSession, symbol: str, now: float) -> bool:
    """새로 지불했으면 True, 이미 이 라운드에 산 종목이면 False.

    재무는 라운드 내내 바뀌지 않는다. 같은 값을 두 번 팔면 그냥 함정이다.
    """
    _check_unlocked(sess, now)
    _check_symbol(symbol)
    if symbol in sess.analyzed_symbols:
        return False
    if sess.company_analyses_left <= 0:
        raise TradeError(
            "no_company_analyses_left", "이 라운드의 기업분석 횟수를 다 썼습니다."
        )
    sess.company_analyses_left -= 1
    sess.analyzed_symbols.add(symbol)
    return True


# --------------------------------------------------------------- 라운드

def goal_reached(sess: GameSession) -> bool:
    """목표는 현금이다. 파산은 총자산이다 — 잣대를 통일하지 않는다.

    목표는 "레이스를 얼마나 달렸나" 라 팔아서 확정한 것만 세고,
    파산은 "아직 게임을 할 수 있나" 라 주식도 함께 센다.

    이것이 매도에 의미를 준다. 총자산 기준이면 사서 오르기만 해도 이기므로
    팔 이유가 없다 — 매도가 장식이 된다.
    """
    return sess.cash >= sess.target


def advance_round(sess: GameSession) -> None:
    current = equity(sess)
    sess.round_no += 1
    sess.round_start_equity = current
    sess.target = current * config.TARGET_MULTIPLIER
    sess.analyses_left = config.ANALYSES_PER_ROUND
    sess.company_analyses_left = config.COMPANY_ANALYSES_PER_ROUND
    sess.analyzed_symbols.clear()
    sess.grind_count = 0
    # 새 분기 실적이 적정가를 옮긴다. 지난 라운드에 산 정보가 낡는다.
    # 가격은 건드리지 않는다 — 점프하면 보유 종목 평가액이 순간이동한다.
    engine.reanchor(sess.prices, fundamentals.fair_values(sess.quarter_index))


# --------------------------------------------------- 체결 피드와 거래량

def record_fill(sess: GameSession, tick: int, actor: str, fill: dict) -> None:
    """체결 하나를 피드와 거래량 창에 남긴다.

    fill 의 value 는 가격 영향 계산용 내부 값이라 피드에 싣지 않는다.
    """
    sess.trade_seq += 1
    sess.trades.append({
        "seq": sess.trade_seq,
        "tick": tick,
        "actor": actor,
        "symbol": fill["symbol"],
        "name": config.STOCKS[fill["symbol"]].name,
        "side": fill["side"],
        "qty": fill["qty"],
        "price": fill["price"],
    })
    sess.volume_window.append((tick, fill["symbol"], fill["qty"]))
    sess.volume_total[fill["symbol"]] += fill["qty"]


def prune_volume(sess: GameSession, tick: int) -> None:
    cutoff = tick - config.VOLUME_WINDOW_TICKS
    while sess.volume_window and sess.volume_window[0][0] < cutoff:
        sess.volume_window.popleft()


def volume_of(sess: GameSession, symbol: str) -> int:
    return sum(qty for _, sym, qty in sess.volume_window if sym == symbol)


def volume_avg_of(sess: GameSession, symbol: str, tick: int) -> int:
    """그때까지의 구간 평균. 프론트가 "평소의 5배" 를 계산하는 기준이다."""
    window = config.VOLUME_WINDOW_TICKS
    return round(sess.volume_total[symbol] * window / max(tick, window))


def ai_rows(sess: GameSession) -> list[dict]:
    """리더보드. 보유 종목은 싣지 않는다 — 체결 피드로 재구성하는 것이 정당한 우위다.

    순위는 총자산 기준이다. 목표 판정이 현금으로 바뀌는 것은 D 와 함께 온다.
    동점은 명단 순서로 가른다 — 임의로 흔들리면 매 폴링마다 리더보드가 요동친다.
    """
    def price(symbol: str) -> int:
        return engine.price_of(sess.prices, symbol)

    scored = [
        (index, ai, participants.equity_of(ai, price))
        for index, ai in enumerate(sess.ais)
    ]
    scored.sort(key=lambda row: (-row[2], row[0]))
    return [
        {
            "id": ai.profile.id,
            "name": ai.profile.name,
            "cash": ai.cash,
            "equity": total,
            "rank": rank,
        }
        for rank, (_, ai, total) in enumerate(scored, start=1)
    ]


# --------------------------------------------------------------- 경주 종료

def winner_of(sess: GameSession) -> str | None:
    """목표에 닿은 사람. 아무도 없으면 None.

    같은 tick 에 둘이 넘으면 플레이어가 먼저다 — 임의로 흔들리면 같은 시드가
    다른 결과를 낸다.
    """
    if sess.cash >= sess.target:
        return "you"
    for ai in sess.ais:
        if ai.cash >= sess.target:
            return ai.profile.name
    return None


def _liquidate_player(sess: GameSession) -> None:
    """보유 전량을 현재가로 판다. 잠금을 검사하지 않는다 — 노가다 중이어도
    경주는 끝나고, 잠금은 매매를 막지 청산을 막지 않는다.
    """
    for symbol in list(sess.holdings):
        gross = engine.price_of(sess.prices, symbol) * sess.holdings[symbol]
        sess.cash += gross - _fee(gross)
    sess.holdings.clear()
    sess.cost_basis.clear()


def finish_race(sess: GameSession, winner: str) -> None:
    """전원 강제 매도 후 순위를 확정한다.

    승자는 **매도 전에** 정해져 있다. 그래서 승자의 최종 현금이 2위보다 적을
    수 있다 — 목표선을 막 넘은 사람과, 주식을 잔뜩 들고 있다가 강제 매도로 큰
    현금을 쥔 사람이 있을 때 그렇다. 의도한 것이다: 목표는 먼저 확정한 사람의
    것이고, 그래서 익절을 미루는 데 대가가 있다.

    수수료도 부과한다 — 미리 팔아둔 사람이 유리해야 익절 판단에 의미가 생긴다.
    """
    _liquidate_player(sess)
    for ai in sess.ais:
        for symbol in list(ai.holdings):
            participants.sell_all(ai, symbol, engine.price_of(sess.prices, symbol))

    rows = [{"name": "나", "cash": sess.cash, "is_player": True}]
    rows += [
        {"name": ai.profile.name, "cash": ai.cash, "is_player": False}
        for ai in sess.ais
    ]

    def is_winner(row: dict) -> bool:
        return row["is_player"] if winner == "you" else row["name"] == winner

    champion = next(row for row in rows if is_winner(row))
    rest = sorted((r for r in rows if r is not champion), key=lambda r: -r["cash"])

    sess.status = "finished"
    sess.winner = winner
    sess.ranking = [
        {**row, "rank": rank} for rank, row in enumerate([champion, *rest], start=1)
    ]
