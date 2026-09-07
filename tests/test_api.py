import math

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import _refilling, app, sessions

# 뉴스는 12~18초 간격으로 등장하므로 tick 0 에는 아직 한 건도 보이지 않는다.
# 뉴스가 필요한 테스트는 started_at 을 과거로 밀어 시간을 흐르게 만든다.
ELAPSED = 120


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
    assert body["target"] == config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER
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


def test_grind_requires_bankruptcy(client):
    sid = start(client)["session_id"]
    response = client.post("/api/grind", json={"session_id": sid})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "not_bankrupt"


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


def test_next_round_requires_reaching_the_goal(client):
    sid = start(client)["session_id"]
    response = client.post("/api/next-round", json={"session_id": sid})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "goal_not_reached"


def test_next_round_triples_the_target_and_refills_analyses(client):
    sid = start(client)["session_id"]
    sess = sessions[sid]
    sess.cash = sess.target
    sess.analyses_left = 0

    response = client.post("/api/next-round", json={"session_id": sid})
    assert response.status_code == 200
    body = response.json()
    assert body["round_no"] == 2
    assert body["analyses_left"] == config.ANALYSES_PER_ROUND
    assert body["target"] == sess.round_start_equity * config.ROUND_TARGET_MULTIPLIER


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

    body = start(client, ELAPSED)
    sid = body["session_id"]
    sess = main.sessions[sid]

    # 고른 기사의 램프가 막 시작된 시점으로 시계를 맞춘다. 어떤 기사가 마침
    # 램프 중이었는지에 기대지 않도록 결정론적으로 세운다.
    item = sess.news[0]
    ramp_end = item.plan.publish_tick + item.plan.ramp_seconds
    sess.started_at = _time.monotonic() - (item.plan.publish_tick + 1)

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
