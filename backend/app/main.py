"""FastAPI 라우트. 계산 로직은 담지 않는다.

GET /api/state 요청이 tick 을 증분 진행한다. 같은 세션의 동시 요청이
tick 을 두 번 밀지 않도록 세션마다 asyncio.Lock 을 하나 둔다.
"""
import asyncio
import os
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import (
    analysis,
    company_analysis,
    config,
    engine,
    fallback,
    fundamentals,
    news,
    participants,
    session as rules,
)
from app.models import NewsPlan
from app.scenario import build_plans
from app.session import GameSession, TradeError


def _build_client():
    """키가 없으면 None — 그 경우 어댑터가 폴백으로 떨어진다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    return anthropic.Anthropic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 클라이언트는 프로세스 수명 동안 하나만 둔다. 호출마다 새로 만들면
    # 연결 풀과 스레드가 서버 수명 내내 쌓인다.
    app.state.claude = _build_client()
    try:
        yield
    finally:
        client = getattr(app.state, "claude", None)
        if client is not None and hasattr(client, "close"):
            client.close()


app = FastAPI(title="모의주식게임", lifespan=lifespan)

sessions: dict[str, GameSession] = {}
_locks: dict[str, asyncio.Lock] = {}


def _client():
    # lifespan 이 돌지 않은 채 임포트만 된 경우에도 None 으로 안전하게 떨어진다.
    return getattr(app.state, "claude", None)


def _get(session_id: str) -> GameSession:
    sess = sessions.get(session_id)
    if sess is None:
        raise HTTPException(404, {"code": "no_session", "message": "게임이 만료됐습니다."})
    # 요청이 닿을 때마다 수명을 갱신한다. 폴링 중인 판은 절대 쓸려나가지 않는다.
    sess.last_seen = time.monotonic()
    return sess


def _sweep(now: float) -> int:
    """오래 조용한 세션을 버린다. DB 가 없으므로 아무도 안 지우면 영원히 남는다.

    세션만 지우고 락과 보충 표시를 남기면 누수가 그대로다 — 함께 정리한다.
    """
    dead = [
        sid for sid, sess in sessions.items()
        if now - sess.last_seen > config.SESSION_IDLE_SECONDS
    ]
    for sid in dead:
        sessions.pop(sid, None)
        _locks.pop(sid, None)
        _refilling.discard(sid)
    return len(dead)


def _lock(session_id: str) -> asyncio.Lock:
    return _locks.setdefault(session_id, asyncio.Lock())


def _fail(error: TradeError) -> HTTPException:
    status = 423 if error.code == "locked" else 400
    return HTTPException(status, {"code": error.code, "message": error.message})


def _tick_of(sess: GameSession, now: float) -> int:
    """5의 배수로 끊은 tick. 시세는 이 주기로만 앞으로 간다.

    tick 단위는 여전히 1초다 — 램프·AI 반응·앵커가 전부 이 단위로 쓰여 있고,
    엔진을 5초 단위로 바꾸면 그것들이 함께 5배 길어져 밸런스가 무너진다.
    관측 시점만 끊으면 보이는 결과는 같고 의미는 하나도 안 바뀐다.
    """
    elapsed = int((now - sess.started_at) / config.TICK_SECONDS)
    return elapsed // config.TICK_QUANTUM * config.TICK_QUANTUM


def _sync(sess: GameSession, now: float) -> int:
    """tick 을 현재까지 진행하고 노가다 보수를 정산한다.

    AI 매매는 tick 루프 안에서 돈다 — 매수가 그 tick 의 가격을 밀고, 그것이
    다음 tick 의 AI 판단에 들어간다. engine 은 순주문액만 받는다.
    """
    tick = _tick_of(sess, now)

    def on_tick(at: int) -> dict[str, int]:
        return participants.run_tick(
            sess.ais, sess.plans, at, sess.ai_seed,
            lambda symbol: engine.price_of(sess.prices, symbol),
            lambda actor, fill: rules.record_fill(sess, at, actor, fill),
        )

    engine.advance(sess.prices, sess.plans, tick, sess.rng, on_tick=on_tick)
    rules.prune_volume(sess, tick)
    rules.settle_grind(sess, now)
    return tick


def _stock_rows(sess: GameSession, tick: int) -> list[dict]:
    rows = []
    for symbol, stock in config.STOCKS.items():
        price = engine.price_of(sess.prices, symbol)
        rows.append({
            "symbol": symbol,
            "name": stock.name,
            "sector": stock.sector,
            "price": price,
            # 표시용 백분율이라 돈의 내림 규칙에서 면제된다. 어떤 판정에도 쓰이지 않는다.
            # 기준은 그 판의 시작가다 — 시작가는 판마다 다르다.
            "change_pct": round(
                (price / sess.prices.start_price[symbol] - 1) * 100, 2
            ),
            "held": sess.holdings.get(symbol, 0),
            "fundamentals_analyzed": symbol in sess.analyzed_symbols,
            # 평단과 가격 이력은 서버가 들고 있다. 새로고침해도 남는다.
            # 안 들고 있으면 null 이다 — 0 을 주면 프론트가 틀린 손익을 그린다.
            "avg_cost": rules.avg_cost_of(sess, symbol),
            "history": engine.history_of(sess.prices, symbol),
            "volume": rules.volume_of(sess, symbol),
            "volume_avg": rules.volume_avg_of(sess, symbol, tick),
        })
    return rows


def _news_rows(sess: GameSession, tick: int, since: int) -> list[dict]:
    """등장한 뉴스만, since 보다 큰 것만. impact/kind 는 절대 싣지 않는다."""
    rows = []
    for item in sess.news:
        if item.plan.publish_tick > tick or item.plan.news_id <= since:
            continue
        rows.append({
            "news_id": item.plan.news_id,
            "symbol": item.plan.symbol,
            "name": config.STOCKS[item.plan.symbol].name,
            "sector": config.STOCKS[item.plan.symbol].sector,
            "headline": item.headline,
            "body": item.body,
            "age_seconds": tick - item.plan.publish_tick,
            "analyzed": item.analyzed,
            "commentary": item.commentary,
            "offline": item.offline,
        })
    return rows


def _trade_rows(sess: GameSession, trades_since: int) -> list[dict]:
    return [row for row in sess.trades if row["seq"] > trades_since]


def _snapshot(
    sess: GameSession, now: float, since: int = -1, trades_since: int = -1
) -> dict:
    tick = _sync(sess, now)
    return {
        "session_id": sess.session_id,
        "tick": tick,
        "round_no": sess.round_no,
        "cash": sess.cash,
        "equity": rules.equity(sess),
        "target": sess.target,
        "analyses_left": sess.analyses_left,
        "company_analyses_left": sess.company_analyses_left,
        "ai": rules.ai_rows(sess),
        "trades": _trade_rows(sess, trades_since),
        "bankrupt": rules.is_bankrupt(sess),
        "locked": rules.is_locked(sess, now),
        "lock_remaining": rules.lock_remaining(sess, now),
        "grind_count": sess.grind_count,
        "goal_reached": rules.goal_reached(sess),
        "stocks": _stock_rows(sess, tick),
        "news": _news_rows(sess, tick, since),
        "news_total": len(sess.news),
    }


_refilling: set[str] = set()


def _pending_count(sess: GameSession, tick: int) -> int:
    """아직 등장하지 않은 뉴스 건수."""
    return sum(1 for plan in sess.plans if plan.publish_tick > tick)


def _next_batch_plans(sess: GameSession, count: int) -> list[NewsPlan]:
    last_tick = sess.plans[-1].publish_tick if sess.plans else 0
    # 단계는 뉴스 배치 번호다. 긴 경주일수록 함정이 늘어난다.
    stage = len(sess.plans) // config.NEWS_BATCH_SIZE + 1
    return build_plans(
        count,
        stage,
        sess.rng,
        first_news_id=len(sess.plans),
        first_tick=last_tick,
    )


async def _refill(sess: GameSession, count: int) -> None:
    """다음 배치의 문장을 받아 이어붙인다. 같은 세션에 두 번 겹쳐 돌지 않게 막는다."""
    if sess.session_id in _refilling:
        return
    _refilling.add(sess.session_id)
    try:
        plans = _next_batch_plans(sess, count)
        # rng 는 이벤트 루프 스레드의 engine.advance 가 동시에 쓴다. 같은 인스턴스를
        # 워커 스레드에 넘기면 random.Random 의 내부 상태(gauss 캐시 포함)에 스레드
        # 경계를 넘는 경합이 생긴다. 워커에는 여기서 파생한 독립 인스턴스를 준다.
        worker_rng = random.Random(sess.rng.random())
        items = await asyncio.to_thread(news.fetch_news, plans, worker_rng, _client())
        sess.plans.extend(plans)
        sess.news.extend(items)
    finally:
        _refilling.discard(sess.session_id)


class SessionBody(BaseModel):
    session_id: str


class TradeBody(SessionBody):
    symbol: str
    side: str
    qty: int


class AnalyzeBody(SessionBody):
    news_id: int


class CompanyAnalyzeBody(SessionBody):
    symbol: str


class NewGameBody(BaseModel):
    ai_count: int = config.AI_COUNT_DEFAULT


@app.post("/api/game")
async def new_game(
    background: BackgroundTasks, body: NewGameBody | None = None
) -> dict:
    # 본문 없이 부르는 기존 클라이언트를 깨지 않는다.
    ai_count = body.ai_count if body is not None else config.AI_COUNT_DEFAULT
    if not config.AI_COUNT_MIN <= ai_count <= config.AI_COUNT_MAX:
        raise HTTPException(400, {
            "code": "bad_ai_count",
            "message": f"AI 수는 {config.AI_COUNT_MIN}~{config.AI_COUNT_MAX} 입니다.",
        })

    now = time.monotonic()
    # 새 판을 만들 때가 버려진 판을 치우기 좋은 순간이다. 타이머를 따로 돌리지 않는다.
    _sweep(now)

    session_id = uuid.uuid4().hex
    rng = random.Random()
    sess = rules.new_session(session_id, rng, started_at=now, ai_count=ai_count)

    # 첫 배치만 기다린다. 20건을 한 번에 기다리면 게임 시작이 10초를 넘는다.
    first = build_plans(
        config.NEWS_FIRST_WAIT_COUNT, 1, rng,
        first_news_id=0, first_tick=0,
    )
    sess.plans.extend(first)
    # rng 는 이벤트 루프 스레드의 engine.advance 가 동시에 쓴다. 같은 인스턴스를
    # 워커 스레드에 넘기면 random.Random 의 내부 상태(gauss 캐시 포함)에 스레드
    # 경계를 넘는 경합이 생긴다. 워커에는 여기서 파생한 독립 인스턴스를 준다.
    worker_rng = random.Random(rng.random())
    sess.news.extend(
        await asyncio.to_thread(news.fetch_news, first, worker_rng, _client())
    )
    sessions[session_id] = sess
    background.add_task(
        _refill, sess, config.NEWS_BATCH_SIZE - config.NEWS_FIRST_WAIT_COUNT
    )
    return _snapshot(sess, now)


@app.get("/api/state")
async def get_state(
    session_id: str,
    background: BackgroundTasks,
    since: int = -1,
    trades_since: int = -1,
) -> dict:
    sess = _get(session_id)
    async with _lock(session_id):
        snapshot = _snapshot(sess, time.monotonic(), since, trades_since)
    # 등장 대기분이 마르기 전에 다음 배치를 채운다. 게임 플로우는 막지 않는다.
    if _pending_count(sess, snapshot["tick"]) <= config.NEWS_REFILL_THRESHOLD:
        background.add_task(_refill, sess, config.NEWS_BATCH_SIZE)
    return snapshot


@app.post("/api/trade")
async def trade(body: TradeBody) -> dict:
    sess = _get(body.session_id)
    if body.side not in ("buy", "sell"):
        raise HTTPException(400, {"code": "bad_side", "message": "side 는 buy 또는 sell 입니다."})
    async with _lock(body.session_id):
        now = time.monotonic()
        _sync(sess, now)
        action = rules.buy if body.side == "buy" else rules.sell
        try:
            result = action(sess, body.symbol, body.qty, now)
        except TradeError as error:
            raise _fail(error) from error
        value = result["gross"] if body.side == "buy" else -result["gross"]
        rules.record_fill(sess, _tick_of(sess, now), "you", {
            "side": result["side"], "symbol": result["symbol"],
            "qty": result["qty"], "price": result["price"], "value": value,
        })
        # 플레이어의 주문도 가격을 민다. 큰 주문일수록 불리하게 체결된다.
        engine.add_flow(sess.prices, result["symbol"], value)
        result["cash"] = sess.cash
        result["equity"] = rules.equity(sess)
        return result


@app.post("/api/analyze")
async def analyze(body: AnalyzeBody) -> dict:
    sess = _get(body.session_id)

    # 예산 차감까지만 락 안에서. 호출 자체는 락 밖에서 기다린다 —
    # 락을 쥔 채 기다리면 같은 세션의 /api/state 폴링이 멈춰 시장이 얼어붙고,
    # "기다리는 몇 초가 분석의 실질 비용" 이라는 규칙이 무효가 된다.
    async with _lock(body.session_id):
        now = time.monotonic()
        tick = _sync(sess, now)
        item = next(
            (i for i in sess.news if i.plan.news_id == body.news_id), None
        )
        if item is None or item.plan.publish_tick > tick:
            raise HTTPException(404, {"code": "no_news", "message": "없는 기사입니다."})
        try:
            rules.spend_analysis(sess, now)
        except TradeError as error:
            raise _fail(error) from error

    commentary, offline = await asyncio.to_thread(
        analysis.fetch_commentary, item, _client()
    )

    # 호출이 도는 동안 시장은 흘렀다. 남은 램프는 지금 시점으로 다시 센다.
    async with _lock(body.session_id):
        now = time.monotonic()
        tick = _sync(sess, now)
        item.analyzed = True
        item.commentary = commentary
        strength = fallback.strength_of(item.plan.impact)
        remaining = engine.ramp_remaining(item.plan, tick)
        return {
            "news_id": item.plan.news_id,
            "strength": strength,
            "label": fallback.STRENGTH_LABELS[strength],
            "commentary": commentary,
            "ramp_remaining": remaining,
            "already_priced_in": remaining == 0,
            "offline": offline,
            "analyses_left": sess.analyses_left,
        }


@app.post("/api/company-analysis")
async def company_analyze(body: CompanyAnalyzeBody) -> dict:
    sess = _get(body.session_id)

    # analyze 와 같은 락 패턴이다. 예산 차감까지만 락 안에서, 호출은 락 밖에서.
    # 락을 쥔 채 기다리면 같은 세션의 /api/state 폴링이 멈춰 시장이 얼어붙는다.
    async with _lock(body.session_id):
        now = time.monotonic()
        _sync(sess, now)
        try:
            rules.spend_company_analysis(sess, body.symbol, now)
        except TradeError as error:
            raise _fail(error) from error

        # 판정을 락 안에서 확정한다. 밖에서 읽으면 다른 요청이 그 사이 tick 을
        # 밀어, 응답의 gap_pct 와 current_price 가 서로 다른 순간을 가리킬 수 있다.
        #
        # analyze 는 반대로 호출이 끝난 뒤 남은 램프를 다시 잰다 — 램프는 시간에
        # 닳는 자원이라 기다린 만큼 줄어드는 것이 맞다. 적정가는 라운드 내내
        # 고정이라 다시 잴 것이 없다.
        stock = config.STOCKS[body.symbol]
        quarter = fundamentals.quarter_of(
            fundamentals.load(), body.symbol, sess.quarter_index
        )
        price = engine.price_of(sess.prices, body.symbol)
        fair = fundamentals.fair_value(body.symbol, quarter)
        gap = fundamentals.gap_pct(price, fair)
        valuation = fundamentals.valuation_of(gap)
        financials = {
            "quarter": quarter["label"],
            "revenue": quarter["revenue"],
            "operating_income": quarter["operating_income"],
            "net_income": quarter["net_income"],
            "eps": fundamentals.eps(quarter),
            "per": fundamentals.per_of(price, quarter),
            "debt_ratio": fundamentals.debt_ratio(quarter),
        }
        left = sess.company_analyses_left

    commentary, offline = await asyncio.to_thread(
        company_analysis.fetch_commentary,
        stock.name, stock.sector, valuation, gap, financials, _client(),
    )

    return {
        "symbol": body.symbol,
        "name": stock.name,
        "fair_value": fair,
        "current_price": price,
        "gap_pct": gap,
        "valuation": valuation,
        "label": fundamentals.VALUATION_LABELS[valuation],
        "financials": financials,
        "commentary": commentary,
        "offline": offline,
        "company_analyses_left": left,
    }


@app.post("/api/grind")
async def grind(body: SessionBody) -> dict:
    sess = _get(body.session_id)
    async with _lock(body.session_id):
        now = time.monotonic()
        _sync(sess, now)
        try:
            info = rules.start_grind(sess, now)
        except TradeError as error:
            raise _fail(error) from error
        return {
            "payout": info["payout"],
            "lock_remaining": rules.lock_remaining(sess, now),
            "grind_count": sess.grind_count,
        }


if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
