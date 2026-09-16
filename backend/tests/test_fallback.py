import random

import pytest

from app import config, fallback
from app.fallback import (
    STRENGTH_LABELS,
    strength_of,
    write_commentary,
    write_news,
    _NEGATIVE_BODIES,
    _NEGATIVE_HEADLINES,
    _POSITIVE_BODIES,
    _POSITIVE_HEADLINES,
)
from app.models import BoardPlan, NewsPlan
from app.scenario import build_plans


@pytest.mark.parametrize("impact,expected", [
    (0.15,  "up_strong"),
    (0.08,  "up_strong"),
    (0.0799, "up_weak"),
    (0.02,  "up_weak"),
    (0.0199, "none"),
    (0.0,   "none"),
    (-0.0199, "none"),
    (-0.02, "down_weak"),
    (-0.0799, "down_weak"),
    (-0.08, "down_strong"),
    (-0.15, "down_strong"),
])
def test_strength_boundaries(impact, expected):
    assert strength_of(impact) == expected


def test_every_strength_has_a_korean_label():
    for key in ("up_strong", "up_weak", "none", "down_weak", "down_strong"):
        assert STRENGTH_LABELS[key]


def test_exaggerated_news_always_grades_as_no_effect():
    """과장 기사의 임팩트 상한이 무영향 경계 아래에 있어야 한다."""
    assert config.IMPACT_RANGES["exaggerated"][1] < config.STRENGTH_WEAK_MIN
    plans = build_plans(60, 1, random.Random(4), first_news_id=0, first_tick=0)
    for p in (p for p in plans if p.kind == "exaggerated"):
        assert strength_of(p.impact) == "none"


def test_write_news_returns_one_item_per_plan_in_order():
    plans = build_plans(12, 1, random.Random(5), first_news_id=0, first_tick=0)
    items = write_news(plans, random.Random(5))
    assert len(items) == len(plans)
    assert [i.plan for i in items] == plans


def test_written_news_is_marked_offline_and_has_text():
    plans = build_plans(8, 1, random.Random(6), first_news_id=0, first_tick=0)
    for item in write_news(plans, random.Random(6)):
        assert item.offline is True
        assert item.headline.strip()
        assert item.body.strip()
        assert item.analyzed is False


def test_headline_names_the_planned_company():
    plans = build_plans(8, 1, random.Random(7), first_news_id=0, first_tick=0)
    for item in write_news(plans, random.Random(7)):
        assert config.STOCKS[item.plan.symbol].name in item.headline


def test_headline_tone_follows_surface_tone_not_the_real_impact():
    """역방향 기사의 문장은 표면 톤을 따라야 한다 — 그래야 함정이 성립한다."""
    plans = build_plans(60, 1, random.Random(8), first_news_id=0, first_tick=0)
    items = write_news(plans, random.Random(8))
    positives = {i.headline for i in items if i.plan.surface_tone == "positive"}
    negatives = {i.headline for i in items if i.plan.surface_tone == "negative"}
    assert positives and negatives
    assert positives.isdisjoint(negatives)


def test_commentary_states_the_verdict_label():
    plans = build_plans(20, 1, random.Random(9), first_news_id=0, first_tick=0)
    for item in write_news(plans, random.Random(9)):
        text = write_commentary(item)
        assert STRENGTH_LABELS[strength_of(item.plan.impact)] in text
        assert len(text) > 10


def test_commentary_never_leaks_the_raw_impact_number():
    plan = NewsPlan(0, "geno", "positive", "reversed", -0.0937, 20, 0)
    items = write_news([plan], random.Random(1))
    text = write_commentary(items[0])
    assert "0.0937" not in text
    assert "-0.09" not in text


def test_text_is_identical_across_kinds_for_the_same_tone_and_seed():
    """같은 톤·종목·시드면 kind 와 impact 가 무엇이든 문장이 완전히 동일해야 한다.

    문장 선택이 숨겨진 정답에 조금이라도 의존하면 이 테스트가 반드시 깨진다.
    헤드라인과 본문을 함께 보므로 표본 운에 의존하지 않는다.
    """
    produced = set()
    for kind, impact in (("honest", 0.14), ("exaggerated", 0.004), ("reversed", -0.11)):
        plan = NewsPlan(0, "geno", "positive", kind, impact, 20, 0)
        item = write_news([plan], random.Random(99))[0]
        produced.add((item.headline, item.body))
    assert len(produced) == 1, "문장이 kind/impact 에 따라 달라진다 — 낚시가 읽기로 들통난다"


def test_generated_text_comes_only_from_the_tone_matched_pools():
    """문장은 반드시 그 표면 톤의 풀에서만 나와야 한다.

    위 테스트는 "정답에 의존하지 않음" 을 보장하고, 이 테스트는 "톤에는 제대로
    의존함" 을 보장한다. 두 풀을 똑같이 만들어버리는 회귀는 이쪽만 잡는다.
    """
    stock = config.STOCKS["geno"]
    pools = {
        "positive": (_POSITIVE_HEADLINES, _POSITIVE_BODIES),
        "negative": (_NEGATIVE_HEADLINES, _NEGATIVE_BODIES),
    }
    for tone, (headlines, bodies) in pools.items():
        allowed_headlines = {t.format(name=stock.name) for t in headlines}
        allowed_bodies = {t.format(sector=stock.sector) for t in bodies}
        for kind, impact in (("honest", 0.14), ("exaggerated", 0.004), ("reversed", -0.11)):
            plan = NewsPlan(0, "geno", tone, kind, impact, 20, 0)
            item = write_news([plan], random.Random(7))[0]
            assert item.headline in allowed_headlines, (tone, kind)
            assert item.body in allowed_bodies, (tone, kind)


# ------------------------------------------------------------ 종토방 글

def _board_plan(bullish=True, author="김부장", post_id=0):
    return BoardPlan(
        post_id=post_id, news_id=0, ai_index=7, author=author,
        symbol="geno", bullish=bullish, publish_tick=40,
    )


def test_board_fallback_writes_one_body_per_plan():
    plans = [_board_plan(post_id=i) for i in range(5)]
    posts = fallback.write_posts(plans, random.Random(0))
    assert len(posts) == 5
    assert all(p.body.strip() for p in posts)
    assert all(p.offline for p in posts)


def test_board_fallback_is_deterministic():
    plans = [_board_plan(post_id=i) for i in range(4)]
    first = [p.body for p in fallback.write_posts(plans, random.Random(3))]
    second = [p.body for p in fallback.write_posts(plans, random.Random(3))]
    assert first == second


def test_board_fallback_tone_follows_the_view():
    bull = fallback.write_posts([_board_plan(bullish=True)], random.Random(1))[0]
    bear = fallback.write_posts([_board_plan(bullish=False)], random.Random(1))[0]
    assert bull.body != bear.body


def test_board_fallback_never_names_the_verdict():
    """글은 의견이지 판정이 아니다. 등급 어휘가 새면 분석이 무의미해진다."""
    banned = ("역방향", "과장", "정직", "함정", "impact", "통찰력")
    plans = [_board_plan(bullish=b, post_id=i) for i, b in enumerate([True, False] * 8)]
    for post in fallback.write_posts(plans, random.Random(2)):
        for word in banned:
            assert word not in post.body


def test_board_fallback_does_not_claim_an_action():
    """샀는지는 체결 피드가 보여준다. 글은 의견만 말한다."""
    plans = [_board_plan(bullish=b, post_id=i) for i, b in enumerate([True, False] * 8)]
    for post in fallback.write_posts(plans, random.Random(4)):
        assert "매수했" not in post.body and "매도했" not in post.body
