import json
import math

import pytest
from fastapi.testclient import TestClient

from app import config, fundamentals
from app.main import _refilling, app, sessions

# 뉴스는 약 30초 간격으로 등장하므로 tick 0 에는 아직 한 건도 보이지 않는다.
# 뉴스가 필요한 테스트는 started_at 을 과거로 밀어 시간을 흐르게 만든다.
# 분석 5회를 소진하는 테스트가 있으므로 기사 5건이 확실히 나올 만큼 흘려보낸다.
ELAPSED = 240


@pytest.fixture(autouse=True)
def clean_sessions():
    sessions.clear()
    _refilling.clear()
    yield
    sessions.clear()
    _refilling.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def start(client, elapsed: int = 0) -> dict:
    """게임을 시작하고, elapsed 초가 흐른 것으로 만든다 (sleep 없이)."""
    response = client.post("/api/game")
    assert response.status_code == 200
    body = response.json()
    if elapsed:
        sessions[body["session_id"]].started_at -= elapsed
    return body


def state(client, session_id: str, since: int = -1) -> dict:
    response = client.get(f"/api/state?session_id={session_id}&since={since}")
    assert response.status_code == 200
    return response.json()


def test_new_game_returns_seed_state(client):
    body = start(client)
    assert body["cash"] == config.SEED_CASH
    assert body["equity"] == config.SEED_CASH
    assert body["round_no"] == 1
    assert body["target"] == config.SEED_CASH * config.TARGET_MULTIPLIER
    assert body["analyses_left"] == config.ANALYSES_PER_ROUND
    assert len(body["stocks"]) == len(config.STOCKS)
    assert body["session_id"]


def test_no_news_has_appeared_at_tick_zero(client):
    """뉴스는 시간이 지나야 뜬다. 시작 화면이 비어 있는 것이 정상이다."""
    body = start(client)
    assert body["tick"] == 0
    assert body["news"] == []
    assert body["news_total"] >= config.NEWS_FIRST_WAIT_COUNT


def test_news_appears_as_time_passes(client):
    body = start(client, ELAPSED)
    appeared = state(client, body["session_id"])["news"]
    assert len(appeared) >= config.ANALYSES_PER_ROUND
    for row in appeared:
        assert row["headline"].strip()
        assert row["name"] in {s.name for s in config.STOCKS.values()}


def test_refill_keeps_the_pipeline_from_running_dry(client):
    """등장 대기분이 임계 아래로 내려가면 다음 배치가 채워진다."""
    body = start(client, ELAPSED)
    sid = body["session_id"]
    before = state(client, sid)["news_total"]
    sessions[sid].started_at -= 600          # 더 흐르게 만든다
    state(client, sid)                       # 보충이 걸린다
    assert state(client, sid)["news_total"] > before


def test_state_never_exposes_impact_or_kind(client):
    """정답이 응답에 실리면 F12 한 번으로 게임이 무너진다."""
    body = start(client, ELAPSED)
    snapshot = state(client, body["session_id"])
    assert snapshot["news"], "뉴스가 없으면 이 테스트는 아무것도 검증하지 못한다"
    blob = str(snapshot)
    assert "impact" not in blob
    assert "honest" not in blob
    assert "exaggerated" not in blob
    assert "reversed" not in blob
    assert "ramp_seconds" not in blob
    assert "publish_tick" not in blob


def test_buy_then_state_reflects_the_position(client):
    body = start(client)
    sid = body["session_id"]
    symbol = "geno"
    price = next(s["price"] for s in body["stocks"] if s["symbol"] == symbol)

    trade = client.post("/api/trade", json={
        "session_id": sid, "symbol": symbol, "side": "buy", "qty": 3,
    })
    assert trade.status_code == 200
    assert trade.json()["fee"] == math.floor(price * 3 * config.TRADE_FEE_RATE)

    holding = next(
        s for s in state(client, sid)["stocks"] if s["symbol"] == symbol
    )
    assert holding["held"] == 3


def test_insufficient_cash_returns_400_with_a_code(client):
    sid = start(client)["session_id"]
    response = client.post("/api/trade", json={
        "session_id": sid, "symbol": "geno", "side": "buy", "qty": 10_000,
    })
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "insufficient_cash"
    assert response.json()["detail"]["message"]


@pytest.mark.parametrize("qty", [0, -3])
def test_non_positive_quantity_returns_the_documented_400(client, qty):
    """수량 거부도 다른 거부와 같은 {code, message} 400 이어야 한다.

    Pydantic 제약을 두면 라우트 본문 전에 422 로 잘려 계약이 한 입력에서만 달라진다.
    """
    sid = start(client)["session_id"]
    response = client.post("/api/trade", json={
        "session_id": sid, "symbol": "geno", "side": "buy", "qty": qty,
    })
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_quantity"
    assert response.json()["detail"]["message"]


def test_unknown_session_returns_404(client):
    response = client.get("/api/state?session_id=nope")
    assert response.status_code == 404


def test_analyze_spends_budget_and_returns_a_verdict(client):
    body = start(client, ELAPSED)
    sid = body["session_id"]
    news_id = state(client, sid)["news"][0]["news_id"]

    response = client.post("/api/analyze", json={"session_id": sid, "news_id": news_id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["strength"] in (
        "up_strong", "up_weak", "none", "down_weak", "down_strong",
    )
    assert payload["label"]
    assert payload["commentary"].strip()
    assert payload["analyses_left"] == config.ANALYSES_PER_ROUND - 1


def test_analyze_beyond_the_budget_returns_400(client):
    body = start(client, ELAPSED)
    sid = body["session_id"]
    news_ids = [n["news_id"] for n in state(client, sid)["news"]]
    assert len(news_ids) >= config.ANALYSES_PER_ROUND

    for news_id in news_ids[: config.ANALYSES_PER_ROUND]:
        assert client.post(
            "/api/analyze", json={"session_id": sid, "news_id": news_id}
        ).status_code == 200

    response = client.post(
        "/api/analyze", json={"session_id": sid, "news_id": news_ids[0]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "no_analyses_left"


def test_analyze_unknown_news_returns_404(client):
    sid = start(client)["session_id"]
    response = client.post("/api/analyze", json={"session_id": sid, "news_id": 99999})
    assert response.status_code == 404


def test_grind_is_open_without_bankruptcy(client):
    """평소에도 누를 수 있다. 파산은 더 이상 전제가 아니다."""
    sid = start(client)["session_id"]
    response = client.post("/api/grind", json={"session_id": sid})
    assert response.status_code == 200
    body = response.json()
    assert body["payout"] > 0
    assert body["grind_count"] == 1
    assert body["lock_remaining"] > 0


def test_grind_still_locks_out_trading(client):
    """상시로 열렸어도 잠금은 그대로다 — 이게 노가다의 값이다."""
    sid = start(client)["session_id"]
    client.post("/api/grind", json={"session_id": sid})
    response = client.post("/api/trade", json={"session_id": sid, "symbol": "geno",
                                               "side": "buy", "qty": 1})
    assert response.status_code == 423
    assert response.json()["detail"]["code"] == "locked"


def test_grind_locks_trading_and_state_reports_it(client):
    sid = start(client)["session_id"]
    sessions[sid].cash = 50_000
    sessions[sid].holdings = {}

    grind = client.post("/api/grind", json={"session_id": sid})
    assert grind.status_code == 200
    assert grind.json()["payout"] == config.GRIND_BASE_PAYOUT

    snapshot = state(client, sid)
    assert snapshot["locked"] is True
    assert 0 < snapshot["lock_remaining"] <= config.GRIND_LOCK_SECONDS

    blocked = client.post("/api/trade", json={
        "session_id": sid, "symbol": "taesan", "side": "buy", "qty": 1,
    })
    assert blocked.status_code == 423
    assert blocked.json()["detail"]["code"] == "locked"


def test_grind_pays_out_once_the_lock_expires(client):
    sid = start(client)["session_id"]
    sess = sessions[sid]
    sess.cash = 50_000
    sess.holdings = {}
    client.post("/api/grind", json={"session_id": sid})

    # 시각을 과거로 밀어 잠금을 만료시킨다 — sleep 없이.
    sess.grind_until -= config.GRIND_LOCK_SECONDS + 1

    snapshot = state(client, sid)
    assert snapshot["locked"] is False
    assert snapshot["cash"] == 50_000 + config.GRIND_BASE_PAYOUT


def test_state_since_returns_only_newer_news(client):
    body = start(client, ELAPSED)
    sid = body["session_id"]
    highest = max(n["news_id"] for n in state(client, sid)["news"])
    assert state(client, sid, since=highest)["news"] == []


def test_state_advances_ticks_over_time(client):
    sid = start(client, ELAPSED)["session_id"]
    assert state(client, sid)["tick"] >= ELAPSED // config.TICK_SECONDS


def test_analysis_does_not_hold_the_session_lock(client, monkeypatch):
    """호출이 도는 동안 락을 쥐고 있으면 같은 세션의 폴링이 막혀 시장이 얼어붙는다.

    시장이 멈추면 "기다리는 몇 초가 분석의 실질 비용" 이라는 규칙이 무효가 되고
    분석이 공짜가 된다. 호출 시점의 락 상태를 직접 관찰한다 — 프록시가 아니라
    성질 자체를 단정하므로, 락을 다시 호출 전체에 걸치면 이 테스트가 반드시 깨진다.
    """
    body = start(client, ELAPSED)
    sid = body["session_id"]
    news_id = state(client, sid)["news"][0]["news_id"]

    import app.main as main

    real = main.analysis.fetch_commentary
    observed = {}

    def probe(item, client_obj):
        # asyncio.to_thread 의 워커 스레드에서 돈다. 이 순간 락이 잡혀 있으면
        # 같은 세션의 다른 요청이 전부 막혀 있다는 뜻이다.
        observed["locked"] = main._locks[sid].locked()
        return real(item, client_obj)

    monkeypatch.setattr(main.analysis, "fetch_commentary", probe)

    response = client.post(
        "/api/analyze", json={"session_id": sid, "news_id": news_id}
    )

    assert response.status_code == 200
    assert observed["locked"] is False, "분석 호출 중 세션 락이 잡혀 있다"
    assert response.json()["commentary"].strip()


def test_ramp_remaining_is_measured_after_the_call_returns(client, monkeypatch):
    """남은 램프는 호출이 끝난 시점으로 재야 한다 — 요청 시작 시점의 낡은 창이 아니라.

    호출 중에 램프가 끝나고도 남을 만큼 시간을 흘려보낸 뒤, analyze 응답 자체의
    ramp_remaining 을 단정한다. 이후의 별도 폴링을 보면 tick 이 무상태로 다시
    계산되므로 낡은 값을 쓰는 구현에서도 통과한다.
    """
    import time as _time

    import app.main as main

    body = start(client)
    sid = body["session_id"]
    sess = main.sessions[sid]

    # 고른 기사의 램프가 막 시작된 시점으로 시계를 맞춘다. 어떤 기사가 마침
    # 램프 중이었는지에 기대지 않도록 결정론적으로 세운다.
    #
    # tick 은 TICK_QUANTUM 의 배수로 내림되므로, 공개 시각 바로 다음 양자에
    # 맞춘다. publish_tick + 1 로 잡으면 내림되어 아직 공개 전이 될 수 있다.
    item = sess.news[0]
    ramp_end = item.plan.publish_tick + item.plan.ramp_seconds
    q = config.TICK_QUANTUM
    target_tick = (item.plan.publish_tick // q + 1) * q
    sess.started_at = _time.monotonic() - target_tick

    pre_tick = state(client, sid)["tick"]
    assert pre_tick < ramp_end, "설정이 틀렸다 — 호출 전에 이미 램프가 끝났다"

    shift = item.plan.ramp_seconds + 10   # 호출 중 램프가 확실히 끝난다
    real = main.analysis.fetch_commentary

    def slow(item_arg, client_obj):
        sess.started_at -= shift
        return real(item_arg, client_obj)

    monkeypatch.setattr(main.analysis, "fetch_commentary", slow)

    payload = client.post(
        "/api/analyze", json={"session_id": sid, "news_id": item.plan.news_id}
    ).json()

    stale = max(0, ramp_end - pre_tick)
    assert stale > 0, "두 값이 구분되지 않는 설정이다"
    assert payload["ramp_remaining"] == 0
    assert payload["already_priced_in"] is True


# ------------------------------------------------------------ 기업분석

def analyze_company(client, session_id: str, symbol: str):
    return client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": symbol}
    )


def test_snapshot_reports_company_analyses_left(client):
    snapshot = start(client)
    assert snapshot["company_analyses_left"] == config.COMPANY_ANALYSES_PER_ROUND
    assert all(row["fundamentals_analyzed"] is False for row in snapshot["stocks"])


def test_snapshot_never_leaks_fair_value(client):
    """적정가가 스냅샷에 실리면 F12 한 번으로 기업분석이 무의미해진다."""
    snapshot = start(client, ELAPSED)
    raw = json.dumps(snapshot, ensure_ascii=False)
    assert "fair_value" not in raw
    assert "valuation" not in raw


def test_company_analysis_returns_the_verdict(client):
    sid = start(client)["session_id"]
    body = analyze_company(client, sid, "geno").json()

    assert body["symbol"] == "geno"
    assert body["name"] == config.STOCKS["geno"].name
    assert body["fair_value"] > 0
    assert body["valuation"] in fundamentals.VALUATION_LABELS
    assert body["label"] == fundamentals.VALUATION_LABELS[body["valuation"]]
    assert body["commentary"].strip()
    assert body["company_analyses_left"] == config.COMPANY_ANALYSES_PER_ROUND - 1
    # 분기는 판마다 다르다. 세션이 고른 것과 일치해야 한다.
    picked = fundamentals.quarter_of(
        fundamentals.load(), "geno", sessions[sid].quarter_index
    )
    assert body["financials"]["quarter"] == picked["label"]


def test_company_analysis_verdict_matches_the_prices(client):
    """등급이 실제 가격·적정가와 어긋나면 앵커와 모순된다."""
    sid = start(client)["session_id"]
    body = analyze_company(client, sid, "geno").json()

    expected_gap = fundamentals.gap_pct(body["current_price"], body["fair_value"])
    assert body["gap_pct"] == expected_gap
    assert body["valuation"] == fundamentals.valuation_of(expected_gap)


def test_company_analysis_marks_the_stock_in_the_snapshot(client):
    sid = start(client)["session_id"]
    analyze_company(client, sid, "geno")

    rows = {row["symbol"]: row for row in state(client, sid)["stocks"]}
    assert rows["geno"]["fundamentals_analyzed"] is True
    assert rows["hanbit"]["fundamentals_analyzed"] is False


def test_company_analysis_is_free_the_second_time(client):
    sid = start(client)["session_id"]
    first = analyze_company(client, sid, "geno").json()
    second = analyze_company(client, sid, "geno").json()
    assert second["company_analyses_left"] == first["company_analyses_left"]
    assert second["fair_value"] == first["fair_value"]


def test_company_analysis_runs_out(client):
    sid = start(client)["session_id"]
    for symbol in list(config.STOCKS)[: config.COMPANY_ANALYSES_PER_ROUND]:
        assert analyze_company(client, sid, symbol).status_code == 200
    remaining = list(config.STOCKS)[config.COMPANY_ANALYSES_PER_ROUND]

    response = analyze_company(client, sid, remaining)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "no_company_analyses_left"


def test_company_analysis_rejects_unknown_symbol(client):
    sid = start(client)["session_id"]
    response = analyze_company(client, sid, "nope")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_symbol"


def test_company_analysis_does_not_hold_the_session_lock(client, monkeypatch):
    """해설을 기다리는 동안 락을 쥐면 같은 세션의 폴링이 막혀 시장이 얼어붙는다.

    analyze 와 같은 성질이다. 호출 시점의 락 상태를 직접 관찰한다 — 프록시가
    아니라 성질 자체를 단정하므로, 락을 호출 전체에 걸치면 반드시 깨진다.
    """
    sid = start(client, ELAPSED)["session_id"]

    import app.main as main

    real = main.company_analysis.fetch_commentary
    observed = {}

    def probe(name, sector, valuation, gap, financials, client_obj):
        # asyncio.to_thread 의 워커 스레드에서 돈다.
        observed["locked"] = main._locks[sid].locked()
        return real(name, sector, valuation, gap, financials, client_obj)

    monkeypatch.setattr(main.company_analysis, "fetch_commentary", probe)

    response = analyze_company(client, sid, "geno")

    assert response.status_code == 200
    assert observed["locked"] is False, "기업분석 호출 중 세션 락이 잡혀 있다"
    assert response.json()["commentary"].strip()


def test_company_analysis_rejects_a_dead_session(client):
    response = analyze_company(client, "없는세션", "geno")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_session"


# ------------------------------------------------- 가격 이력과 평단

def test_stocks_carry_no_average_cost_before_buying(client):
    """0 이 아니라 null 이어야 한다. 0 이면 프론트가 틀린 손익을 그린다."""
    for row in start(client)["stocks"]:
        assert row["avg_cost"] is None


def test_stocks_carry_the_average_cost_after_buying(client):
    sid = start(client, ELAPSED)["session_id"]
    client.post("/api/trade", json={"session_id": sid, "symbol": "geno",
                                    "side": "buy", "qty": 5})

    rows = {r["symbol"]: r for r in state(client, sid)["stocks"]}
    assert rows["geno"]["avg_cost"] > 0
    assert rows["hanbit"]["avg_cost"] is None


def test_stocks_carry_price_history(client):
    sid = start(client, ELAPSED)["session_id"]
    for row in state(client, sid)["stocks"]:
        assert isinstance(row["history"], list)
        assert 0 < len(row["history"]) <= config.PRICE_HISTORY_TICKS
        # 마지막 값이 현재가여야 차트와 호가가 어긋나지 않는다
        assert row["history"][-1] == row["price"]


def test_history_survives_a_fresh_poll(client):
    """이게 이 작업의 목적이다 — 새로고침해도 차트가 남는다."""
    sid = start(client, ELAPSED)["session_id"]
    first = state(client, sid)["stocks"][0]["history"]
    # 새 클라이언트가 처음 붙은 것과 같은 요청
    again = state(client, sid)["stocks"][0]["history"]
    assert len(again) >= len(first) > 1


def test_history_never_grows_past_the_window(client):
    sid = start(client, 600)["session_id"]        # 10분을 한 번에 따라잡는다
    for row in state(client, sid)["stocks"]:
        assert len(row["history"]) == config.PRICE_HISTORY_TICKS


# ------------------------------------------------------------ AI 참가자

def test_game_seats_the_default_ai_count(client):
    body = start(client)
    assert len(body["ai"]) == config.AI_COUNT_DEFAULT
    assert body["trades"] == []


def test_game_without_a_body_still_works(client):
    """프론트가 지금 본문 없이 부르고 있다. 깨지면 안 된다."""
    response = client.post("/api/game")
    assert response.status_code == 200
    assert len(response.json()["ai"]) == config.AI_COUNT_DEFAULT


def test_game_accepts_an_ai_count(client):
    response = client.post("/api/game", json={"ai_count": 9})
    assert response.status_code == 200
    assert len(response.json()["ai"]) == 9


@pytest.mark.parametrize("count", [0, -1, 10, 100])
def test_game_rejects_an_out_of_range_ai_count(client, count):
    response = client.post("/api/game", json={"ai_count": count})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_ai_count"


def test_ai_rows_carry_a_rank_and_no_holdings(client):
    body = start(client)
    for row in body["ai"]:
        assert set(row) == {"id", "name", "cash", "equity", "rank"}
    assert sorted(r["rank"] for r in body["ai"]) == list(
        range(1, config.AI_COUNT_DEFAULT + 1)
    )


def test_ais_actually_trade_once_time_passes(client):
    sid = start(client, ELAPSED)["session_id"]
    body = state(client, sid)
    assert body["trades"], "120초가 흘렀는데 AI 가 한 번도 안 움직였다"
    assert all(t["actor"] != "you" for t in body["trades"])


def test_trades_since_filters_like_since(client):
    sid = start(client, ELAPSED)["session_id"]
    highest = max(t["seq"] for t in state(client, sid)["trades"])
    response = client.get(f"/api/state?session_id={sid}&trades_since={highest}")
    assert all(t["seq"] > highest for t in response.json()["trades"])


def test_player_trades_appear_in_the_feed(client):
    sid = start(client, ELAPSED)["session_id"]
    client.post("/api/trade", json={"session_id": sid, "symbol": "geno",
                                    "side": "buy", "qty": 1})
    mine = [t for t in state(client, sid)["trades"] if t["actor"] == "you"]
    assert len(mine) == 1
    assert mine[0]["side"] == "buy" and mine[0]["qty"] == 1


def test_stocks_report_volume(client):
    sid = start(client, ELAPSED)["session_id"]
    for row in state(client, sid)["stocks"]:
        assert row["volume"] >= 0
        assert row["volume_avg"] >= 0


def test_snapshot_never_exposes_ai_holdings(client):
    raw = json.dumps(start(client, ELAPSED), ensure_ascii=False)
    assert "holdings" not in raw
    assert "cursor" not in raw


def test_more_ais_means_more_trades(client):
    few = client.post("/api/game", json={"ai_count": 1}).json()
    sessions[few["session_id"]].started_at -= ELAPSED
    many = client.post("/api/game", json={"ai_count": 9}).json()
    sessions[many["session_id"]].started_at -= ELAPSED

    quiet = len(state(client, few["session_id"])["trades"])
    loud = len(state(client, many["session_id"])["trades"])
    assert loud > quiet


# ------------------------------------------ 시세 갱신 주기와 세션 수명

def test_price_only_advances_on_the_quantum(client):
    """시세는 5초에 한 번만 앞으로 간다. tick 은 5의 배수여야 한다."""
    for elapsed in (0, 3, 5, 7, 12, 29):
        sid = start(client, elapsed)["session_id"]
        tick = state(client, sid)["tick"]
        assert tick % config.TICK_QUANTUM == 0, f"{elapsed}초 → tick {tick}"
        assert tick <= elapsed


def test_price_is_identical_inside_one_quantum(client):
    """같은 5초 창 안에서는 몇 번을 폴링해도 값이 같다."""
    sid = start(client, 20)["session_id"]
    first = state(client, sid)
    second = state(client, sid)
    assert first["tick"] == second["tick"]
    assert [s["price"] for s in first["stocks"]] == [s["price"] for s in second["stocks"]]


def test_news_comes_about_every_thirty_seconds(client):
    """간격이 촘촘하면 읽을 틈이 없고 메모리도 빨리 찬다."""
    lo, hi = config.NEWS_INTERVAL_RANGE
    assert 28 <= lo <= hi <= 32

    sid = start(client, 300)["session_id"]
    ticks = sorted(300 - n["age_seconds"] for n in state(client, sid)["news"])
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert gaps, "5분이 흘렀는데 기사가 두 건도 안 나왔다"
    assert all(lo - config.TICK_QUANTUM <= g <= hi + config.TICK_QUANTUM for g in gaps), gaps


def test_idle_sessions_are_swept_when_a_new_game_starts(client):
    """세션이 영원히 쌓이면 버려진 판 100개가 100MB 를 먹는다."""
    stale = start(client)["session_id"]
    sessions[stale].last_seen -= config.SESSION_IDLE_SECONDS + 60

    fresh_id = client.post("/api/game").json()["session_id"]

    assert stale not in sessions
    assert fresh_id in sessions
    assert client.get(f"/api/state?session_id={stale}").status_code == 404


def test_a_live_session_survives_the_sweep(client):
    alive = start(client)["session_id"]
    client.post("/api/game")
    assert alive in sessions
    assert client.get(f"/api/state?session_id={alive}").status_code == 200


def test_polling_keeps_a_session_alive(client):
    sid = start(client)["session_id"]
    sessions[sid].last_seen -= config.SESSION_IDLE_SECONDS + 60
    state(client, sid)                       # 폴링이 수명을 갱신한다
    client.post("/api/game")
    assert sid in sessions


def test_sweeping_also_drops_the_lock_and_refill_marks(client):
    """세션만 지우고 부속을 남기면 누수가 그대로다."""
    import app.main as main
    stale = start(client)["session_id"]
    state(client, stale)                     # 락을 만든다
    assert stale in main._locks
    sessions[stale].last_seen -= config.SESSION_IDLE_SECONDS + 60

    client.post("/api/game")

    assert stale not in main._locks
    assert stale not in main._refilling


def test_next_round_is_gone(client):
    """한 판 = 한 경주다. 라운드 전환이 낄 자리가 없다."""
    sid = start(client)["session_id"]
    response = client.post("/api/next-round", json={"session_id": sid})
    assert response.status_code in (404, 405)


def test_snapshot_has_no_round_start_equity(client):
    body = start(client)
    assert "round_start_equity" not in body
    # round_no 는 프론트 호환을 위해 1 로 남는다. 프론트 전환 때 지운다.
    assert body["round_no"] == 1


# ------------------------------------------------------------ 경주 종료

def _win(client, sid):
    """플레이어를 목표에 올려놓고 한 번 폴링해 종료를 일으킨다."""
    sessions[sid].cash = sessions[sid].target
    return state(client, sid)


def test_a_fresh_game_is_running(client):
    body = start(client)
    assert body["status"] == "running"
    assert body["ranking"] is None
    assert body["winner"] is None


def test_reaching_the_target_finishes_the_game(client):
    sid = start(client, ELAPSED)["session_id"]
    body = _win(client, sid)

    assert body["status"] == "finished"
    assert body["winner"] == "you"
    assert len(body["ranking"]) == config.AI_COUNT_DEFAULT + 1
    assert body["ranking"][0]["is_player"] is True


def test_an_ai_reaching_the_target_finishes_the_game(client):
    sid = start(client, ELAPSED)["session_id"]
    sessions[sid].ais[0].cash = sessions[sid].target
    body = state(client, sid)

    assert body["status"] == "finished"
    assert body["winner"] == sessions[sid].ais[0].profile.name
    assert body["ranking"][0]["is_player"] is False


def test_holdings_are_liquidated_on_finish(client):
    sid = start(client, ELAPSED)["session_id"]
    client.post("/api/trade", json={"session_id": sid, "symbol": "geno",
                                    "side": "buy", "qty": 2})
    _win(client, sid)

    assert sessions[sid].holdings == {}
    assert all(not ai.holdings for ai in sessions[sid].ais)


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/trade", {"symbol": "geno", "side": "buy", "qty": 1}),
        ("/api/analyze", {"news_id": 0}),
        ("/api/company-analysis", {"symbol": "geno"}),
        ("/api/grind", {}),
    ],
)
def test_a_finished_game_rejects_everything(client, path, payload):
    sid = start(client, ELAPSED)["session_id"]
    _win(client, sid)

    response = client.post(path, json={"session_id": sid, **payload})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "game_finished"


def test_a_finished_game_still_serves_state(client):
    """결과를 봐야 한다."""
    sid = start(client, ELAPSED)["session_id"]
    _win(client, sid)
    assert state(client, sid)["status"] == "finished"


def test_catching_up_ends_where_polling_would(client):
    """**이 작업에서 가장 깨지기 쉬운 성질이다.**

    탭을 비웠다 돌아온 요청이 폴링과 같은 지점에서 끝나야 한다. 뒤에서 한 번만
    검사하면 따라잡기가 경주를 지나쳐 계속 굴러가고 승자가 달라진다.
    """
    sid = start(client, ELAPSED)["session_id"]
    sess = sessions[sid]
    sess.ais[0].cash = sess.target

    sess.started_at -= 1800
    body = state(client, sid)

    assert body["status"] == "finished"
    assert body["tick"] < 1800


def test_time_stops_when_the_game_ends(client):
    sid = start(client, ELAPSED)["session_id"]
    frozen = _win(client, sid)["tick"]

    sessions[sid].started_at -= 60
    assert state(client, sid)["tick"] == frozen
