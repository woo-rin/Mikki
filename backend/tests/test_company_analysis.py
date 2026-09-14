import pytest

from app import company_analysis, fallback, fundamentals

FINANCIALS = {
    "quarter": "2024Q1",
    "revenue": 81_200_000_000,
    "operating_income": 16_500_000_000,
    "net_income": 12_800_000_000,
    "eps": 1032,
    "per": 43.7,
    "debt_ratio": 40.0,
}


def _commentary(valuation="overvalued", gap=15.0, financials=None):
    return fallback.write_company_commentary(
        "제노셀", "바이오", valuation, gap, financials or FINANCIALS
    )


def test_fallback_covers_every_valuation():
    for valuation in fundamentals.VALUATION_LABELS:
        assert _commentary(valuation=valuation).strip()


def test_fallback_names_the_verdict():
    assert fundamentals.VALUATION_LABELS["overvalued"] in _commentary("overvalued")


def test_fallback_handles_a_loss_making_quarter():
    """per 가 None 이어도 문장이 나와야 한다."""
    financials = {**FINANCIALS, "net_income": -3_200_000_000, "eps": -259, "per": None}
    assert _commentary(valuation="fair", financials=financials).strip()


def test_fetch_falls_back_when_client_is_none():
    text, offline = company_analysis.fetch_commentary(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS, None
    )
    assert offline is True
    assert text.strip()


class _Boom:
    class messages:
        @staticmethod
        def parse(**kwargs):
            raise RuntimeError("네트워크가 죽었다")


def test_fetch_falls_back_when_the_call_raises():
    text, offline = company_analysis.fetch_commentary(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS, _Boom()
    )
    assert offline is True
    assert text.strip()


class _Refusal:
    class messages:
        @staticmethod
        def parse(**kwargs):
            return type("R", (), {"stop_reason": "refusal", "parsed_output": None})()


def test_fetch_falls_back_on_refusal():
    text, offline = company_analysis.fetch_commentary(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS, _Refusal()
    )
    assert offline is True
    assert text.strip()


class _Empty:
    class messages:
        @staticmethod
        def parse(**kwargs):
            parsed = company_analysis.Commentary(commentary="   ")
            return type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()


def test_fetch_falls_back_on_blank_commentary():
    text, offline = company_analysis.fetch_commentary(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS, _Empty()
    )
    assert offline is True
    assert text.strip()


class _Good:
    class messages:
        @staticmethod
        def parse(**kwargs):
            parsed = company_analysis.Commentary(commentary="섹터 평균 대비 배수가 높다.")
            return type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()


def test_fetch_returns_the_model_text_when_it_works():
    text, offline = company_analysis.fetch_commentary(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS, _Good()
    )
    assert offline is False
    assert text == "섹터 평균 대비 배수가 높다."


def test_prompt_carries_the_settled_verdict():
    """분석은 뉴스와 반대다 — 정답을 전부 넘기고 근거만 설명하게 한다."""
    prompt = company_analysis.build_company_prompt(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS
    )
    assert fundamentals.VALUATION_LABELS["overvalued"] in prompt
    assert "제노셀" in prompt


def test_prompt_never_leaks_the_fair_value():
    """적정가 숫자가 프롬프트에 있으면 Claude 가 문장에 흘린다.

    등급만 사려던 플레이어가 덤으로 정확한 숫자를 받게 된다.
    """
    prompt = company_analysis.build_company_prompt(
        "제노셀", "바이오", "overvalued", 15.0, FINANCIALS
    )
    assert "39216" not in prompt.replace(",", "")


def test_prompt_never_invites_a_reverdict():
    assert "다시 판단" in company_analysis.SYSTEM
