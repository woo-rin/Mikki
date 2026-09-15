import json
import math

import pytest

from app import config, fundamentals


def test_snapshot_has_every_symbol_with_four_quarters():
    snapshot = fundamentals.load()
    for symbol in config.STOCKS:
        quarters = snapshot["stocks"][symbol]["quarters"]
        assert len(quarters) == 4, f"{symbol} 의 분기가 4개가 아니다"


def test_snapshot_never_leaks_the_real_company():
    """corp_code 나 종목코드가 새면 매핑이 역추적된다."""
    raw = json.dumps(fundamentals.load(), ensure_ascii=False)
    assert "corp_code" not in raw
    assert "stock_code" not in raw


def test_eps_is_net_income_over_shares():
    quarter = {"net_income": 12_800_000_000, "shares": 12_400_000,
               "revenue": 81_200_000_000}
    assert fundamentals.eps(quarter) == 1032


def test_sps_is_revenue_over_shares():
    quarter = {"net_income": 1, "shares": 12_400_000, "revenue": 76_000_000_000}
    assert fundamentals.sps(quarter) == 6129


def test_fair_value_uses_sector_per_when_profitable():
    quarter = {"net_income": 12_800_000_000, "shares": 12_400_000,
               "revenue": 81_200_000_000}
    # 바이오 기준 PER 38.0 × EPS 1032
    assert fundamentals.fair_value("geno", quarter) == math.floor(38.0 * 1032)


def test_fair_value_falls_back_to_psr_when_loss_making():
    """적자면 PER 이 음수 적정가를 낳는다. 매출 기준으로 떨어져야 한다."""
    quarter = {"net_income": -3_200_000_000, "shares": 12_400_000,
               "revenue": 76_000_000_000}
    fair = fundamentals.fair_value("geno", quarter)
    assert fair > 0
    # 바이오 기준 PSR 6.5 × SPS 6129
    assert fair == math.floor(6.5 * 6129)


def test_fair_value_of_zero_profit_also_uses_psr():
    """경계값. 0 은 PER 경로로 가면 적정가가 0 이 된다."""
    quarter = {"net_income": 0, "shares": 12_400_000, "revenue": 76_000_000_000}
    assert fundamentals.fair_value("geno", quarter) == math.floor(6.5 * 6129)


def test_fair_value_is_a_floored_integer():
    for symbol in config.STOCKS:
        for index in range(4):
            fair = fundamentals.fair_values(index)[symbol]
            assert isinstance(fair, int)
            assert fair > 0


def test_first_quarter_fair_values_are_exactly_these():
    """스냅샷 전사 오류를 여기서 잡는다. 밸런스의 기준점이다."""
    assert fundamentals.fair_values(0) == {
        "hanbit": 81_928,
        "geno": 39_216,
        "sungjin": 60_984,
        "pixel": 32_976,
        "taesan": 18_502,
        "arawings": 24_002,
    }


def test_third_quarter_uses_the_psr_path_for_geno():
    """인덱스 2 의 geno 는 적자 분기다."""
    assert fundamentals.fair_values(2)["geno"] == 39_838


def test_quarter_index_is_clamped_to_what_exists():
    """범위 밖을 줘도 죽지 않는다. 있는 것 중 가장 가까운 것으로 붙인다."""
    assert fundamentals.fair_values(99) == fundamentals.fair_values(3)
    assert fundamentals.fair_values(-5) == fundamentals.fair_values(0)


def test_quarter_count_matches_the_snapshot():
    assert fundamentals.quarter_count() == 4


def test_quarter_of_is_zero_indexed():
    snapshot = fundamentals.load()
    assert fundamentals.quarter_of(snapshot, "geno", 0)["label"] == "2024Q1"
    assert fundamentals.quarter_of(snapshot, "geno", 2)["label"] == "2024Q3"


def test_gap_pct_is_positive_when_overvalued():
    assert fundamentals.gap_pct(45_100, 39_216) == 15.0
    assert fundamentals.gap_pct(30_000, 39_216) < 0


@pytest.mark.parametrize(
    "gap,expected",
    [
        (40.0, "severely_overvalued"),
        (25.0, "severely_overvalued"),
        (24.9, "overvalued"),
        (10.0, "overvalued"),
        (9.9, "fair"),
        (0.0, "fair"),
        (-9.9, "fair"),
        (-10.0, "undervalued"),
        (-24.9, "undervalued"),
        (-25.0, "severely_undervalued"),
        (-40.0, "severely_undervalued"),
    ],
)
def test_valuation_boundaries(gap, expected):
    assert fundamentals.valuation_of(gap) == expected


def test_every_valuation_has_a_korean_label():
    for gap in (40.0, 15.0, 0.0, -15.0, -40.0):
        assert fundamentals.VALUATION_LABELS[fundamentals.valuation_of(gap)]


def test_per_is_none_when_loss_making():
    """적자 기업의 PER 은 숫자를 만들어내지 않고 비운다."""
    quarter = {"net_income": -3_200_000_000, "shares": 12_400_000,
               "revenue": 76_000_000_000}
    assert fundamentals.per_of(40_000, quarter) is None


def test_per_and_debt_ratio():
    quarter = {"net_income": 12_800_000_000, "shares": 12_400_000,
               "revenue": 81_200_000_000,
               "equity": 240_000_000_000, "debt": 96_000_000_000}
    assert fundamentals.per_of(45_100, quarter) == 43.7
    assert fundamentals.debt_ratio(quarter) == 40.0


def test_every_sector_has_both_multiples():
    """섹터를 늘렸는데 배수를 빠뜨리면 KeyError 가 런타임에 터진다."""
    for stock in config.STOCKS.values():
        assert stock.sector in config.SECTOR_PER
        assert stock.sector in config.SECTOR_PSR
