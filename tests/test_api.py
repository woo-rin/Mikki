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


def test_market_keeps_moving_while_analysis_runs(client, monkeypatch):
    """분석 호출 중에 시장이 멈추면 '기다리는 시간이 분석의 비용' 규칙이 무효가 된다."""
    body = start(client, ELAPSED)
    sid = body["session_id"]
    news_id = state(client, sid)["news"][0]["news_id"]
    before = state(client, sid)["tick"]

    # 호출이 도는 동안 5초가 흐른 것으로 만든다.
    import app.main as main

    real = main.analysis.fetch_commentary

    def slow(item, client_obj):
        main.sessions[sid].started_at -= 5
        return real(item, client_obj)

    monkeypatch.setattr(main.analysis, "fetch_commentary", slow)

    payload = client.post(
        "/api/analyze", json={"session_id": sid, "news_id": news_id}
    ).json()

    assert state(client, sid)["tick"] >= before + 5
    assert payload["commentary"].strip()
