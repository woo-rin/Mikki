import random

from app import config
from app.analysis import fetch_commentary
from app.fallback import STRENGTH_LABELS, strength_of
from app.models import NewsPlan
from app.news import NewsBatch, NewsText, build_news_prompt, fetch_news
from app.scenario import build_plans


class FakeMessages:
    """anthropic 클라이언트의 messages.parse 만 흉내낸다."""

    def __init__(self, result=None, error=None, stop_reason="end_turn"):
        self._result = result
        self._error = error
        self._stop_reason = stop_reason
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return type(
            "Response", (), {"parsed_output": self._result, "stop_reason": self._stop_reason}
        )()


class FakeClient:
    def __init__(self, **kwargs):
        self.messages = FakeMessages(**kwargs)


def plans(n=3, seed=1):
    return build_plans(n, 1, random.Random(seed), first_news_id=0, first_tick=0)


# ------------------------------------------------------------------ 뉴스

def test_news_uses_claude_text_when_the_call_succeeds():
    p = plans(2)
    batch = NewsBatch(items=[
        NewsText(headline="첫 기사 제목", body="첫 기사 본문"),
        NewsText(headline="둘째 기사 제목", body="둘째 기사 본문"),
    ])
    client = FakeClient(result=batch)

    items = fetch_news(p, random.Random(0), client)

    assert [i.headline for i in items] == ["첫 기사 제목", "둘째 기사 제목"]
    assert all(i.offline is False for i in items)
    assert [i.plan for i in items] == p


def test_news_prompt_hides_kind_impact_and_ramp():
    """kind 나 impact 가 프롬프트에 새면 문장만 읽고 낚시를 알아채게 된다.

    요청 kwargs 전체가 아니라 프롬프트 문자열만 본다 — 전체를 보면
    max_tokens=16000 의 "16" 이 ramp_seconds 16 과 우연히 겹쳐 헛되게 실패한다.
    """
    p = plans(6, seed=2)
    text = build_news_prompt(p)
    for word in ("honest", "exaggerated", "reversed"):
        assert word not in text
    for plan in p:
        assert f"{plan.impact}" not in text
        assert str(plan.ramp_seconds) not in text


def test_news_prompt_does_include_company_sector_and_tone():
    p = plans(2, seed=3)
    text = build_news_prompt(p)
    for plan in p:
        assert config.STOCKS[plan.symbol].name in text
        assert config.STOCKS[plan.symbol].sector in text
        assert plan.surface_tone in text


def test_system_prompt_forbids_naming_real_entities():
    from app.news import SYSTEM
    assert "가상 기업" in SYSTEM
    assert "실재하" in SYSTEM


def test_news_falls_back_when_the_client_raises():
    p = plans(3)
    items = fetch_news(p, random.Random(0), FakeClient(error=RuntimeError("boom")))
    assert len(items) == 3
    assert all(i.offline is True for i in items)
    assert all(i.headline.strip() for i in items)


def test_news_falls_back_on_refusal():
    p = plans(3)
    client = FakeClient(result=None, stop_reason="refusal")
    items = fetch_news(p, random.Random(0), client)
    assert all(i.offline is True for i in items)


def test_news_falls_back_when_there_is_no_client():
    p = plans(3)
    items = fetch_news(p, random.Random(0), None)
    assert all(i.offline is True for i in items)


def test_news_falls_back_when_claude_returns_the_wrong_count():
    p = plans(3)
    client = FakeClient(result=NewsBatch(items=[NewsText(headline="h", body="b")]))
    items = fetch_news(p, random.Random(0), client)
    assert len(items) == 3
    assert all(i.offline is True for i in items)


def test_news_uses_the_configured_model():
    p = plans(1)
    client = FakeClient(result=NewsBatch(items=[NewsText(headline="h", body="b")]))
    fetch_news(p, random.Random(0), client)
    assert client.messages.calls[0]["model"] == config.MODEL


# ------------------------------------------------------------------ 분석

def make_item(impact=-0.09, kind="reversed", tone="positive"):
    from app.fallback import write_news
    plan = NewsPlan(0, "geno", tone, kind, impact, 20, 0)
    return write_news([plan], random.Random(0))[0]


def test_commentary_uses_claude_text_when_the_call_succeeds():
    from app.analysis import Commentary
    item = make_item()
    client = FakeClient(result=Commentary(commentary="Claude 가 쓴 해설"))
    text, offline = fetch_commentary(item, client)
    assert text == "Claude 가 쓴 해설"
    assert offline is False


def test_analysis_prompt_carries_the_verdict_label_but_not_the_number():
    """분석에는 정답을 알려준다 — Claude 가 판정을 다시 하지 않게.

    단 원시 임팩트 수치는 넣지 않는다. 해설이 소수점을 인용하면 게임이
    수치 계산 게임으로 변한다.
    """
    from app.analysis import build_analysis_prompt
    item = make_item(impact=-0.0937)
    text = build_analysis_prompt(item)
    assert STRENGTH_LABELS[strength_of(item.plan.impact)] in text
    assert item.headline in text
    assert item.body in text
    assert "0.0937" not in text
    assert item.plan.kind not in text


def test_commentary_falls_back_when_the_client_raises():
    item = make_item()
    text, offline = fetch_commentary(item, FakeClient(error=RuntimeError("boom")))
    assert offline is True
    assert STRENGTH_LABELS[strength_of(item.plan.impact)] in text


def test_commentary_falls_back_on_refusal():
    item = make_item()
    client = FakeClient(result=None, stop_reason="refusal")
    text, offline = fetch_commentary(item, client)
    assert offline is True
    assert text.strip()


def test_commentary_falls_back_without_a_client():
    item = make_item()
    text, offline = fetch_commentary(item, None)
    assert offline is True
    assert text.strip()


def test_news_falls_back_when_claude_returns_blank_text():
    """빈 헤드라인이 offline=False 로 플레이어에게 도달하면 그 항목의 낚시가 무효가 된다."""
    p = plans(2)
    client = FakeClient(result=NewsBatch(items=[
        NewsText(headline="  ", body="본문"),
        NewsText(headline="제목", body=""),
    ]))
    items = fetch_news(p, random.Random(0), client)
    assert all(i.offline is True for i in items)
    assert all(i.headline.strip() and i.body.strip() for i in items)


def test_analysis_system_prompt_forbids_naming_real_entities():
    from app.analysis import SYSTEM
    assert "가상 기업" in SYSTEM
    assert "실재하" in SYSTEM
