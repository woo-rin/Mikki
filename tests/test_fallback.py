import random

import pytest

from app import config
from app.fallback import (
    STRENGTH_LABELS,
    strength_of,
    write_commentary,
    write_news,
)
from app.models import NewsPlan
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
