# 펀더멘털 앵커와 기업분석 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실존 기업의 재무로 종목마다 적정가를 만들고, 가격이 거기로 끌리게 하며, 그 적정가를 라운드당 2회 살 수 있는 `기업분석` 을 붙인다.

**Architecture:** 재무는 커밋된 JSON 스냅샷에서 읽는다(런타임 네트워크 호출 없음). `fundamentals` 가 적정가와 등급을 계산하고, `engine` 이 tick 마다 Ornstein–Uhlenbeck 평균회귀 항으로 가격을 적정가 쪽으로 민다. `company_analysis` 가 `analysis` 와 같은 모양으로 Claude 해설을 붙이고, 실패하면 `fallback` 으로 떨어진다.

**Tech Stack:** Python 3.11, FastAPI 0.115.6, pydantic 2.10.4, pytest 8.3.4. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-09-14-fundamentals-anchor-design.md`

**Branch:** `feat/fundamentals-anchor`

## Global Constraints

- **작업 디렉터리는 언제나 `backend/`** 다. 테스트도 서버도 거기서 돈다.
- **테스트는 네트워크도 Claude 도 부르지 않는다.** 기존 122개가 그렇다. 새 테스트도 그래야 한다.
- `pytest.ini` 가 **경고를 오류로 취급한다.** `DeprecationWarning` 하나라도 나면 빨갛게 죽는다.
- **숫자 리터럴은 `config.py` 에만 둔다.** 다른 파일에 밸런스 수치를 적지 않는다.
- **돈은 전부 `math.floor` 내림.** 표시용 백분율(`change_pct`, `gap_pct`, `per`, `debt_ratio`)만 예외이고 이들은 어떤 판정에도 쓰이지 않는다.
- **서버 밖으로 나가지 않는 것:** `impact`, `kind`, `fair_value`, `valuation`. 앞의 둘은 기존 규칙, 뒤의 둘이 이번에 추가된다. `fair_value`/`valuation` 은 `POST /api/company-analysis` 응답에만 실린다.
- **커밋 메시지는 한국어**, 기존 형식(`feat:`, `fix:`, `test:`, `docs:`, `refactor:`)을 따른다.
- 매 태스크는 `.venv/bin/pytest -q` **전체**가 통과한 상태로 끝난다.

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `data/fundamentals.json` | 재무 스냅샷. 커밋한다 | 1 |
| `app/fundamentals.py` | 스냅샷 로딩, 적정가, 등급. 네트워크를 모른다 | 1 |
| `scripts/fetch_fundamentals.py` | DART 호출. **서버가 임포트하지 않는다** | 2 |
| `app/config.py` | 섹터 배수, 앵커 상수. `base_price` 제거 | 1, 3 |
| `app/engine.py` | 시작가·앵커를 `PriceState` 에 들이고 평균회귀 항 추가 | 3, 4 |
| `app/session.py` | 기업분석 횟수, 라운드 재앵커 | 5 |
| `app/fallback.py` | 기업분석 폴백 해설 | 6 |
| `app/company_analysis.py` | Claude 해설. `analysis.py` 와 쌍 | 6 |
| `app/main.py` | 새 엔드포인트, 스냅샷 2필드 | 7 |

의존 순서가 곧 태스크 순서다. **3번이 기존 테스트를 깨뜨리므로 3번 안에서 같이 고친다.**

---

### Task 1: 적정가와 등급

**Files:**
- Create: `backend/data/fundamentals.json`
- Create: `backend/app/fundamentals.py`
- Create: `backend/tests/test_fundamentals.py`
- Modify: `backend/app/config.py` (섹터 배수 추가. `base_price` 는 Task 3 에서 건드린다)

**Interfaces:**
- Consumes: `config.STOCKS` (심볼 → `sector`)
- Produces:
  - `fundamentals.load(path: str | None = None) -> dict`
  - `fundamentals.quarter_of(snapshot: dict, symbol: str, round_no: int) -> dict`
  - `fundamentals.eps(quarter: dict) -> int`
  - `fundamentals.sps(quarter: dict) -> int`
  - `fundamentals.fair_value(symbol: str, quarter: dict) -> int`
  - `fundamentals.fair_values(round_no: int) -> dict[str, int]`
  - `fundamentals.gap_pct(current_price: int, fair: int) -> float`
  - `fundamentals.valuation_of(gap: float) -> str`
  - `fundamentals.per_of(current_price: int, quarter: dict) -> float | None`
  - `fundamentals.debt_ratio(quarter: dict) -> float`
  - `fundamentals.VALUATION_LABELS: dict[str, str]`

- [ ] **Step 1: 스냅샷을 만든다**

`backend/data/fundamentals.json`. 최상위는 `generated_at`, `source`, `stocks` 셋이다. `stocks` 아래 6심볼, 각 심볼에 `mapped_from` 과 `quarters` 4개.

한 심볼의 모양(나머지 5개도 동일):

```json
{
  "generated_at": "2026-09-14",
  "source": "임시 스냅샷 — scripts/fetch_fundamentals.py 로 교체해야 한다",
  "stocks": {
    "geno": {
      "mapped_from": "실존 바이오 중형주",
      "quarters": [
        { "label": "2024Q1", "revenue": 81200000000, "operating_income": 16500000000,
          "net_income": 12800000000, "equity": 240000000000, "debt": 96000000000,
          "shares": 12400000 }
      ]
    }
  }
}
```

전체 수치. **`equity`·`debt`·`shares` 는 심볼마다 4분기 공통**이고, `revenue`/`operating_income`/`net_income` 만 분기별로 다르다. 단위는 원이다.

| 심볼 | shares | equity | debt |
|---|---|---|---|
| `hanbit` | 68,000,000 | 3,200,000,000,000 | 1,100,000,000,000 |
| `geno` | 12,400,000 | 240,000,000,000 | 96,000,000,000 |
| `sungjin` | 44,000,000 | 1,900,000,000,000 | 1,250,000,000,000 |
| `pixel` | 18,000,000 | 310,000,000,000 | 62,000,000,000 |
| `taesan` | 52,000,000 | 1,600,000,000,000 | 2,080,000,000,000 |
| `arawings` | 96,000,000 | 1,450,000,000,000 | 2,320,000,000,000 |

분기별 손익 (단위: 원. 표의 값에 `000000000` 이 아니라 **아래 그대로** 쓴다):

| 심볼 | 분기 | revenue | operating_income | net_income |
|---|---|---|---|---|
| `hanbit` | 2024Q1 | 2650000000000 | 480000000000 | 398000000000 |
| `hanbit` | 2024Q2 | 2780000000000 | 505000000000 | 421000000000 |
| `hanbit` | 2024Q3 | 2510000000000 | 430000000000 | 352000000000 |
| `hanbit` | 2024Q4 | 2900000000000 | 548000000000 | 447000000000 |
| `geno` | 2024Q1 | 81200000000 | 16500000000 | 12800000000 |
| `geno` | 2024Q2 | 88000000000 | 19200000000 | 15100000000 |
| `geno` | 2024Q3 | 76000000000 | -1400000000 | -3200000000 |
| `geno` | 2024Q4 | 94500000000 | 22000000000 | 17600000000 |
| `sungjin` | 2024Q1 | 1740000000000 | 158000000000 | 122000000000 |
| `sungjin` | 2024Q2 | 1690000000000 | 140000000000 | 104000000000 |
| `sungjin` | 2024Q3 | 1820000000000 | 175000000000 | 136000000000 |
| `sungjin` | 2024Q4 | 1905000000000 | 192000000000 | 151000000000 |
| `pixel` | 2024Q1 | 186000000000 | 44000000000 | 37100000000 |
| `pixel` | 2024Q2 | 174000000000 | 38000000000 | 31500000000 |
| `pixel` | 2024Q3 | 198000000000 | 49000000000 | 41200000000 |
| `pixel` | 2024Q4 | 205000000000 | 52000000000 | 44000000000 |
| `taesan` | 2024Q1 | 3200000000000 | 178000000000 | 128300000000 |
| `taesan` | 2024Q2 | 3080000000000 | 160000000000 | 112000000000 |
| `taesan` | 2024Q3 | 3340000000000 | 195000000000 | 141500000000 |
| `taesan` | 2024Q4 | 3410000000000 | 203000000000 | 149200000000 |
| `arawings` | 2024Q1 | 2620000000000 | 295000000000 | 209500000000 |
| `arawings` | 2024Q2 | 2710000000000 | 318000000000 | 228000000000 |
| `arawings` | 2024Q3 | 2480000000000 | 254000000000 | 176400000000 |
| `arawings` | 2024Q4 | 2830000000000 | 341000000000 | 247100000000 |

`mapped_from` 값: `hanbit` = "실존 반도체 대형주", `geno` = "실존 바이오 중형주", `sungjin` = "실존 2차전지 소재주", `pixel` = "실존 게임 퍼블리셔", `taesan` = "실존 건설 중견주", `arawings` = "실존 항공 운송주".

**`geno` 의 2024Q3 는 적자다.** PSR 폴백 경로가 실제로 쓰이도록 일부러 넣었다. 지우지 말 것.

**종목 코드나 `corp_code` 를 넣지 않는다.** 넣으면 매핑이 역추적되어 설계 원칙 5가 무너진다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`backend/tests/test_fundamentals.py`:

```python
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
        for round_no in (1, 2, 3, 4):
            fair = fundamentals.fair_values(round_no)[symbol]
            assert isinstance(fair, int)
            assert fair > 0


def test_round_one_fair_values_are_exactly_these():
    """스냅샷 전사 오류를 여기서 잡는다. 밸런스의 기준점이다."""
    assert fundamentals.fair_values(1) == {
        "hanbit": 81_928,
        "geno": 39_216,
        "sungjin": 60_984,
        "pixel": 32_976,
        "taesan": 18_502,
        "arawings": 24_002,
    }


def test_round_three_uses_the_psr_path_for_geno():
    """3라운드의 geno 는 적자 분기다."""
    assert fundamentals.fair_values(3)["geno"] == 39_838


def test_round_beyond_the_snapshot_reuses_the_last_quarter():
    """라운드 수에 상한이 없다. 분기가 마르면 마지막 것을 계속 쓴다."""
    last = fundamentals.fair_values(4)
    assert fundamentals.fair_values(5) == last
    assert fundamentals.fair_values(99) == last


def test_quarter_of_is_one_indexed():
    snapshot = fundamentals.load()
    assert fundamentals.quarter_of(snapshot, "geno", 1)["label"] == "2024Q1"
    assert fundamentals.quarter_of(snapshot, "geno", 3)["label"] == "2024Q3"


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
```

- [ ] **Step 3: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_fundamentals.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fundamentals'`

- [ ] **Step 4: 섹터 배수를 `config.py` 에 넣는다**

`ANALYSES_PER_ROUND = 5` 아래에 붙인다:

```python
COMPANY_ANALYSES_PER_ROUND = 2

# 섹터 기준 배수. 실제 시장 평균에서 따왔고, 밸런스 손잡이로 쓴다.
# PER 은 흑자 분기에, PSR 은 적자 분기에 쓰인다.
SECTOR_PER: dict[str, float] = {
    "반도체": 14.0,
    "바이오": 38.0,
    "2차전지": 22.0,
    "게임": 16.0,
    "건설": 7.5,
    "항공": 11.0,
}
SECTOR_PSR: dict[str, float] = {
    "반도체": 2.2,
    "바이오": 6.5,
    "2차전지": 2.8,
    "게임": 3.0,
    "건설": 0.5,
    "항공": 1.1,
}

# 등급 경계. 양수가 고평가다.
VALUATION_SEVERE = 25.0
VALUATION_MILD = 10.0
```

- [ ] **Step 5: `app/fundamentals.py` 를 쓴다**

```python
"""재무 스냅샷과 적정가. 네트워크를 모른다 — 커밋된 파일만 읽는다.

적정가는 임팩트와 같은 등급의 정답이다. 상태 스냅샷에 실으면 F12 한 번으로
기업분석이 무의미해진다. 밖으로 내보내는 곳은 기업분석 응답 하나뿐이다.
"""
import json
import math
import pathlib

from app import config

SNAPSHOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "fundamentals.json"

VALUATION_LABELS: dict[str, str] = {
    "severely_overvalued": "심각한 고평가",
    "overvalued": "고평가",
    "fair": "적정",
    "undervalued": "저평가",
    "severely_undervalued": "심각한 저평가",
}

_cache: dict | None = None


def load(path: str | None = None) -> dict:
    """스냅샷을 읽는다. 기본 경로는 프로세스 수명 동안 한 번만 읽는다."""
    global _cache
    if path is not None:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if _cache is None:
        _cache = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return _cache


def quarter_of(snapshot: dict, symbol: str, round_no: int) -> dict:
    """라운드 N 은 quarters[N-1]. 라운드 수에 상한이 없으므로 마르면 마지막을 쓴다."""
    quarters = snapshot["stocks"][symbol]["quarters"]
    return quarters[min(round_no - 1, len(quarters) - 1)]


def eps(quarter: dict) -> int:
    return quarter["net_income"] // quarter["shares"]


def sps(quarter: dict) -> int:
    return quarter["revenue"] // quarter["shares"]


def fair_value(symbol: str, quarter: dict) -> int:
    """흑자면 PER, 적자면 PSR. 원 단위 내림.

    적자 성장주를 매출 기준으로 보는 것은 실제 밸류에이션 실무와 같다.
    PER 을 그대로 쓰면 음수 적정가가 나와 앵커가 가격을 0 아래로 민다.
    """
    sector = config.STOCKS[symbol].sector
    if quarter["net_income"] > 0:
        return math.floor(config.SECTOR_PER[sector] * eps(quarter))
    return math.floor(config.SECTOR_PSR[sector] * sps(quarter))


def fair_values(round_no: int) -> dict[str, int]:
    """그 라운드의 전 종목 적정가."""
    snapshot = load()
    return {
        symbol: fair_value(symbol, quarter_of(snapshot, symbol, round_no))
        for symbol in config.STOCKS
    }


def gap_pct(current_price: int, fair: int) -> float:
    """양수가 고평가다. 표시용이라 내림 규칙에서 면제된다."""
    return round((current_price - fair) / fair * 100, 1)


def valuation_of(gap: float) -> str:
    if gap >= config.VALUATION_SEVERE:
        return "severely_overvalued"
    if gap >= config.VALUATION_MILD:
        return "overvalued"
    if gap > -config.VALUATION_MILD:
        return "fair"
    if gap > -config.VALUATION_SEVERE:
        return "undervalued"
    return "severely_undervalued"


def per_of(current_price: int, quarter: dict) -> float | None:
    """적자면 None. 없는 숫자를 지어내지 않는다."""
    earnings = eps(quarter)
    if earnings <= 0:
        return None
    return round(current_price / earnings, 1)


def debt_ratio(quarter: dict) -> float:
    return round(quarter["debt"] / quarter["equity"] * 100, 1)
```

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 기존 122개 + 새 테스트 전부.

- [ ] **Step 7: 커밋**

```bash
cd backend
git add data/fundamentals.json app/fundamentals.py app/config.py tests/test_fundamentals.py
git commit -m "feat: 재무 스냅샷에서 적정가와 밸류에이션 등급을 낸다

적자 분기는 PER 이 음수 적정가를 낳으므로 PSR 로 떨어진다. geno 의
2024Q3 가 적자라 그 경로가 테스트에서 실제로 밟힌다.

라운드 1 의 적정가 6개를 테스트가 정확한 값으로 못박는다 — 스냅샷
전사 오류를 잡고, 밸런스의 기준점을 고정한다."
```

---

### Task 2: DART 갱신 스크립트

**Files:**
- Create: `backend/scripts/fetch_fundamentals.py`

**Interfaces:**
- Consumes: 없음 (`app` 을 임포트하지 않는다)
- Produces: 없음. **서버도 테스트도 이 파일을 임포트하지 않는다.**

> **왜 테스트가 없나:** 이 스크립트의 전부가 네트워크 호출이다. 모킹해서 테스트하면 DART 응답 형식에 대한 우리 가정만 확인하게 되고, 형식이 바뀌면 테스트는 통과한 채 스크립트가 죽는다. 대신 **실패하면 기존 파일을 덮어쓰지 않고 죽게** 만든다. 반쪽 스냅샷이 커밋되는 것보다 낫다.

- [ ] **Step 1: 스크립트를 쓴다**

```python
"""DART 오픈API 에서 재무를 받아 data/fundamentals.json 을 다시 만든다.

    DART_API_KEY=... python3 scripts/fetch_fundamentals.py

서버는 이 파일을 임포트하지 않는다. 분기에 한 번 손으로 돌린다.

매핑표는 이 파일 안에만 있다. 출력 JSON 에 corp_code 를 넣으면 어느
실존 기업인지 역추적되고, 그러면 가상 이름을 쓰는 의미가 사라진다.
"""
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BASE = "https://opendart.fss.or.kr/api"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "fundamentals.json"

# 가상 심볼 → (실존 corp_code, 사람이 읽는 설명)
# corp_code 는 DART 의 corpCode.xml 에서 찾는다.
MAPPING: dict[str, tuple[str, str]] = {
    "hanbit":   ("00126380", "실존 반도체 대형주"),
    "geno":     ("00105271", "실존 바이오 중형주"),
    "sungjin":  ("00164779", "실존 2차전지 소재주"),
    "pixel":    ("00258801", "실존 게임 퍼블리셔"),
    "taesan":   ("00106641", "실존 건설 중견주"),
    "arawings": ("00113410", "실존 항공 운송주"),
}

# 분기 → DART reprt_code
REPORTS = [("Q1", "11013"), ("Q2", "11012"), ("Q3", "11014"), ("Q4", "11011")]

# 우리가 쓰는 계정명 → DART 계정명 후보 (회사마다 표기가 다르다)
ACCOUNTS = {
    "revenue": ("매출액", "수익(매출액)", "영업수익"),
    "operating_income": ("영업이익", "영업이익(손실)"),
    "net_income": ("당기순이익", "당기순이익(손실)"),
    "equity": ("자본총계",),
    "debt": ("부채총계",),
}


def _get(path: str, **params) -> dict:
    params["crtfc_key"] = os.environ["DART_API_KEY"]
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "000":
        raise RuntimeError(f"{path} 실패: {payload.get('status')} {payload.get('message')}")
    return payload


def _amount(rows: list[dict], names: tuple[str, ...]) -> int:
    for row in rows:
        if row.get("account_nm") in names and row.get("sj_div") in ("IS", "CIS", "BS"):
            raw = (row.get("thstrm_amount") or "").replace(",", "").strip()
            if raw in ("", "-"):
                continue
            return int(raw)
    raise RuntimeError(f"계정을 찾지 못했다: {names}")


def _shares(corp_code: str, year: str) -> int:
    rows = _get("stockTotqySttus.json", corp_code=corp_code,
                bsns_year=year, reprt_code="11011")["list"]
    for row in rows:
        if row.get("se") in ("보통주", "합계"):
            raw = (row.get("istc_totqy") or "").replace(",", "").strip()
            if raw not in ("", "-"):
                return int(raw)
    raise RuntimeError("주식총수를 찾지 못했다")


def build(year: str) -> dict:
    stocks = {}
    for symbol, (corp_code, described_as) in MAPPING.items():
        shares = _shares(corp_code, year)
        quarters = []
        for suffix, reprt_code in REPORTS:
            rows = _get("fnlttSinglAcntAll.json", corp_code=corp_code,
                        bsns_year=year, reprt_code=reprt_code, fs_div="CFS")["list"]
            quarter = {"label": f"{year}{suffix}"}
            for field, names in ACCOUNTS.items():
                quarter[field] = _amount(rows, names)
            quarter["shares"] = shares
            quarters.append(quarter)
        stocks[symbol] = {"mapped_from": described_as, "quarters": quarters}
        print(f"  {symbol}: 4개 분기", file=sys.stderr)
    return stocks


def main() -> int:
    if not os.environ.get("DART_API_KEY"):
        print("DART_API_KEY 가 없다. https://opendart.fss.or.kr 에서 발급받는다.",
              file=sys.stderr)
        return 1
    year = sys.argv[1] if len(sys.argv) > 1 else "2024"
    print(f"{year}년 재무를 받는다…", file=sys.stderr)

    # 전부 성공한 뒤에야 쓴다. 중간에 죽으면 기존 파일은 그대로 남는다.
    stocks = build(year)

    OUT.write_text(
        json.dumps(
            {"generated_at": year, "source": "DART 오픈API", "stocks": stocks},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT} 를 새로 썼다.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 키 없이 돌려 안전하게 죽는지 확인한다**

Run: `cd backend && python3 scripts/fetch_fundamentals.py`
Expected: `DART_API_KEY 가 없다…` 를 출력하고 종료 코드 1. **`data/fundamentals.json` 은 변하지 않아야 한다.**

Run: `cd backend && git status --short data/`
Expected: 출력 없음 (파일이 안 바뀌었다)

- [ ] **Step 3: 전체 테스트가 여전히 통과하는지 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 스크립트는 어디서도 임포트되지 않으므로 아무 영향이 없다.

- [ ] **Step 4: 커밋**

```bash
cd backend
git add scripts/fetch_fundamentals.py
git commit -m "feat: DART 재무 갱신 스크립트

서버도 테스트도 임포트하지 않는다. 분기에 한 번 손으로 돌린다.

매핑표는 이 파일 안에만 둔다 — 출력 JSON 에 corp_code 가 실리면
어느 실존 기업인지 역추적되고 가상 이름을 쓰는 의미가 사라진다.

전부 성공한 뒤에야 파일을 쓴다. 중간에 죽으면 기존 스냅샷이 남는다."
```

> **주의:** `MAPPING` 의 `corp_code` 여섯 개는 형식만 맞는 예시다. 실제로 돌리기 전에 DART 의 `corpCode.xml` 에서 섹터가 맞고 4개 분기가 온전한 회사를 골라 채워야 한다. 그때까지 `data/fundamentals.json` 은 Task 1 의 임시 스냅샷이다.

---

### Task 3: 시작 오프셋 — `base_price` 를 없앤다

**Files:**
- Modify: `backend/app/config.py` (`Stock.base_price` 제거, 오프셋 범위 추가)
- Modify: `backend/app/engine.py` (`PriceState` 확장, `new_state` 시그니처, `price_of`, `reanchor`)
- Modify: `backend/app/session.py:45` (`new_session` 이 적정가를 넘긴다)
- Modify: `backend/app/main.py:94` (`change_pct` 기준)
- Modify: `backend/tests/test_engine.py` (14곳의 `new_state()`, 6곳의 `base_price`)

**Interfaces:**
- Consumes: `fundamentals.fair_values(round_no)` (Task 1)
- Produces:
  - `engine.PriceState(log_return, start_price, anchor_log, last_tick)`
  - `engine.new_state(fair_values: dict[str, int], rng: random.Random) -> PriceState`
  - `engine.price_of(state, symbol) -> int` (시그니처 동일, 기준만 바뀜)
  - `engine.reanchor(state: PriceState, fair_values: dict[str, int]) -> None`

> **이 태스크가 기존 테스트를 깨뜨린다.** 같은 태스크 안에서 고쳐, 끝났을 때 전체가 초록이 되게 한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_engine.py` **맨 위**에 헬퍼를 추가한다. 기존 `new_state()` 호출 14곳을 전부 `_state()` 로 바꾼다:

```python
import random

from app import config, fundamentals


def _state(rng: random.Random | None = None):
    """테스트용 기본 상태. 오프셋 난수를 고정해 결정론을 유지한다."""
    return new_state(fundamentals.fair_values(1), rng or random.Random(12345))
```

`base_price` 를 보던 6곳은 `state.start_price[symbol]` 로 바꾼다. 예를 들어 기존

```python
assert price_of(state, symbol) == stock.base_price
```

는 이렇게 된다:

```python
assert price_of(state, symbol) == state.start_price[symbol]
```

그리고 파일 끝에 새 테스트를 추가한다:

```python
def test_start_price_lands_within_the_offset_band():
    fair = fundamentals.fair_values(1)
    state = _state()
    lo, hi = config.START_OFFSET_RANGE
    for symbol in config.STOCKS:
        ratio = state.start_price[symbol] / fair[symbol]
        assert 1 + lo <= ratio <= 1 + hi


def test_start_offset_is_deterministic_for_a_seed():
    """같은 시드는 같은 판을 만든다. 재현 없이는 밸런스를 못 고친다."""
    fair = fundamentals.fair_values(1)
    first = new_state(fair, random.Random(7))
    second = new_state(fair, random.Random(7))
    assert first.start_price == second.start_price
    assert first.anchor_log == second.anchor_log


def test_start_offset_differs_between_seeds():
    """매판 어느 종목이 고평가인지 달라져야 기업분석이 살아있다."""
    fair = fundamentals.fair_values(1)
    seeds = [new_state(fair, random.Random(seed)).start_price for seed in range(8)]
    assert len({tuple(sorted(s.items())) for s in seeds}) > 1


def test_anchor_log_points_at_the_fair_value():
    fair = fundamentals.fair_values(1)
    state = new_state(fair, random.Random(7))
    for symbol in config.STOCKS:
        implied = state.start_price[symbol] * math.exp(state.anchor_log[symbol])
        assert implied == pytest.approx(fair[symbol], rel=1e-9)


def test_reanchor_moves_the_anchor_but_not_the_price():
    """라운드 전환에 가격이 점프하면 보유 종목 평가액이 순간이동한다."""
    state = _state()
    engine.advance(state, [], 50, random.Random(3))
    before = {symbol: price_of(state, symbol) for symbol in config.STOCKS}
    before_anchor = dict(state.anchor_log)

    engine.reanchor(state, fundamentals.fair_values(2))

    assert {symbol: price_of(state, symbol) for symbol in config.STOCKS} == before
    assert state.anchor_log != before_anchor


def test_price_of_returns_the_start_price_at_tick_zero():
    """정수 시작가는 float 왕복에서 1원도 잃지 않아야 한다."""
    state = _state()
    for symbol in config.STOCKS:
        assert price_of(state, symbol) == state.start_price[symbol]
```

`import math`, `import pytest`, `from app import engine` 가 파일 상단에 없으면 추가한다.

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_engine.py -q`
Expected: FAIL — `new_state() takes 0 positional arguments but 2 were given`

- [ ] **Step 3: `config.py` 에서 `base_price` 를 빼고 오프셋 범위를 넣는다**

`Stock` 에서 `base_price: int` 줄을 지운다:

```python
@dataclass(frozen=True)
class Stock:
    name: str
    sector: str
    volatility: float  # tick당 로그수익 표준편차
```

`STOCKS` 의 각 줄에서 시작가를 뺀다:

```python
STOCKS: dict[str, Stock] = {
    "hanbit":   Stock("한빛솔리드", "반도체",  0.0030),
    "geno":     Stock("제노셀",     "바이오",  0.0040),
    "sungjin":  Stock("성진셀즈",   "2차전지", 0.0030),
    "pixel":    Stock("픽셀로그",   "게임",    0.0025),
    "taesan":   Stock("태산건영",   "건설",    0.0015),
    "arawings": Stock("아라윙스",   "항공",    0.0020),
}
```

`SECTOR_PSR` 아래에 추가한다:

```python
# 시작가는 적정가 대비 이 범위에서 뽑는다. 고정 시작가를 쓰면 어느 종목이
# 고평가인지가 매판 같아서, 한 번 외운 플레이어에게 기업분석이 죽는다.
START_OFFSET_RANGE = (-0.30, 0.30)
```

- [ ] **Step 4: `engine.py` 를 고친다**

```python
@dataclass
class PriceState:
    log_return: dict[str, float] = field(default_factory=dict)
    start_price: dict[str, int] = field(default_factory=dict)
    anchor_log: dict[str, float] = field(default_factory=dict)
    last_tick: int = 0


def new_state(fair_values: dict[str, int], rng: random.Random) -> PriceState:
    """적정가 대비 랜덤 위치에서 출발한다.

    로그가격이 아니라 누적 로그수익을 든다. log(start) 를 저장하면 exp 왕복에서
    1원이 사라진다. 정수 시작가는 정확히 남기고 수익률만 float 로 둔다.
    """
    lo, hi = config.START_OFFSET_RANGE
    start_price: dict[str, int] = {}
    anchor_log: dict[str, float] = {}
    # 종목 순회 순서를 고정해야 같은 시드가 같은 판을 만든다.
    for symbol in config.STOCKS:
        fair = fair_values[symbol]
        start = max(1, math.floor(fair * (1.0 + rng.uniform(lo, hi))))
        start_price[symbol] = start
        anchor_log[symbol] = math.log(fair / start)
    return PriceState(
        log_return={symbol: 0.0 for symbol in config.STOCKS},
        start_price=start_price,
        anchor_log=anchor_log,
        last_tick=0,
    )


def reanchor(state: PriceState, fair_values: dict[str, int]) -> None:
    """적정가만 갱신한다. start_price 와 log_return 은 건드리지 않는다.

    가격이 점프하면 플레이어가 들고 있던 종목의 평가액이 순간이동한다.
    """
    for symbol, fair in fair_values.items():
        state.anchor_log[symbol] = math.log(fair / state.start_price[symbol])
```

`price_of` 의 기준을 바꾼다:

```python
def price_of(state: PriceState, symbol: str) -> int:
    """원 단위 정수. 내림으로 통일한다."""
    return math.floor(state.start_price[symbol] * math.exp(state.log_return[symbol]))
```

- [ ] **Step 5: `session.py` 가 적정가를 넘기게 한다**

`from app import config, engine` 을 `from app import config, engine, fundamentals` 로 바꾸고, `new_session` 을 고친다:

```python
def new_session(session_id: str, rng: random.Random, started_at: float) -> GameSession:
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        prices=engine.new_state(fundamentals.fair_values(1), rng),
        cash=config.SEED_CASH,
        round_start_equity=config.SEED_CASH,
        target=config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER,
    )
```

- [ ] **Step 6: `main.py` 의 `change_pct` 기준을 바꾼다**

`_stock_rows` 안에서:

```python
            # 표시용 백분율이라 돈의 내림 규칙에서 면제된다. 어떤 판정에도 쓰이지 않는다.
            # 기준은 그 판의 시작가다 — 시작가는 판마다 다르다.
            "change_pct": round((price / sess.prices.start_price[symbol] - 1) * 100, 2),
```

- [ ] **Step 7: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 8: 커밋**

```bash
cd backend
git add app/config.py app/engine.py app/session.py app/main.py tests/test_engine.py
git commit -m "feat: 시작가를 적정가 대비 랜덤 위치에서 뽑는다

config 의 고정 base_price 를 없앤다. 고정이면 어느 종목이 고평가인지가
매판 같아서, 한 번 외운 플레이어에게 기업분석이 죽는다.

시작가와 앵커는 PriceState 로 내려간다. change_pct 의 기준도 그 판의
시작가가 된다 — 프론트가 보는 의미는 그대로 '게임 시작 이후 등락률'이다.

reanchor 는 적정가만 갱신하고 가격은 건드리지 않는다. 라운드 전환에
가격이 점프하면 보유 종목 평가액이 순간이동한다."
```

---

### Task 4: 펀더멘털 앵커

**Files:**
- Modify: `backend/app/engine.py` (`advance` 의 tick 루프)
- Modify: `backend/app/config.py` (`ANCHOR_PULL`)
- Modify: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `PriceState.anchor_log` (Task 3)
- Produces: 없음. `advance` 의 시그니처는 그대로다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_engine.py` 끝에 추가한다:

```python
class _NoNoise(random.Random):
    """노이즈를 0 으로 고정한다. 앵커만 따로 관찰하기 위한 것이다."""

    def gauss(self, mu, sigma):
        return 0.0


def test_anchor_pulls_an_overvalued_stock_down():
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 13_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    before = price_of(state, "geno")
    engine.advance(state, [], 60, _NoNoise())
    after = price_of(state, "geno")

    assert after < before
    assert after > fair["geno"]      # 한 번에 도달하지는 않는다


def test_anchor_pushes_an_undervalued_stock_up():
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 7_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    before = price_of(state, "geno")
    engine.advance(state, [], 60, _NoNoise())
    after = price_of(state, "geno")

    assert after > before
    assert after < fair["geno"]


def test_anchor_converges_on_the_fair_value():
    """충분히 오래 두면 적정가에 닿는다."""
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 13_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    engine.advance(state, [], 5_000, _NoNoise())
    assert price_of(state, "geno") == pytest.approx(fair["geno"], rel=0.001)


def test_anchor_never_overshoots():
    """평균회귀는 목표를 지나치지 않는다. 지나치면 진동한다."""
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 13_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    for tick in range(1, 400):
        engine.advance(state, [], tick, _NoNoise())
        assert price_of(state, "geno") >= fair["geno"]


def test_anchor_pulls_back_after_a_ramp_ends():
    """호재가 진짜여도 램프가 끝나면 앵커가 되돌린다. 두 축이 싸운다."""
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 10_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    plan = NewsPlan(
        news_id=0, symbol="geno", surface_tone="positive", kind="honest",
        impact=0.20, ramp_seconds=20, publish_tick=0,
    )
    engine.advance(state, [plan], 20, _NoNoise())
    peak = price_of(state, "geno")
    assert peak > fair["geno"]

    engine.advance(state, [plan], 400, _NoNoise())
    assert price_of(state, "geno") < peak


def test_anchor_is_weaker_than_a_news_ramp():
    """앵커가 뉴스를 이기면 AI 분석 5회의 희소성이 무너진다."""
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 10_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)

    plan = NewsPlan(
        news_id=0, symbol="geno", surface_tone="positive", kind="honest",
        impact=0.10, ramp_seconds=30, publish_tick=0,
    )
    engine.advance(state, [plan], 30, _NoNoise())
    assert price_of(state, "geno") > fair["geno"]


def test_anchor_keeps_incremental_and_bulk_identical():
    """앵커는 난수를 쓰지 않는다. 기존 불변식이 유지돼야 한다."""
    fair = fundamentals.fair_values(1)
    stepwise = new_state(fair, random.Random(7))
    rng = random.Random(99)
    for tick in range(1, 41):
        engine.advance(stepwise, [], tick, rng)

    at_once = new_state(fair, random.Random(7))
    engine.advance(at_once, [], 40, random.Random(99))

    assert stepwise.log_return == at_once.log_return
```

`from app.models import NewsPlan` 이 상단에 없으면 추가한다.

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_engine.py -q -k anchor`
Expected: FAIL — 앵커 항이 없으니 `after < before` 가 거짓이다 (`_NoNoise` 라 가격이 안 움직인다).

- [ ] **Step 3: `config.py` 에 `ANCHOR_PULL` 을 넣는다**

`START_OFFSET_RANGE` 아래:

```python
# tick 당 적정가 쪽으로 당기는 비율. 반감기는 ln(2)/0.004 ≈ 173 tick ≈ 2분 53초다.
#
# 앵커는 절대 뉴스를 이기면 안 된다. 이기면 뉴스가 장식이 되고 AI 분석 5회의
# 희소성이 무너진다. 단일 tick 기여(30% 괴리에서 0.10%)가 노이즈(0.15~0.40%)
# 보다 작아서 즉시 보이지 않고, 방향이 일정해 누적되면 이긴다.
ANCHOR_PULL = 0.004
```

- [ ] **Step 4: `advance` 에 항을 더한다**

`engine.advance` 의 tick 루프를 이렇게 고친다:

```python
    for tick in range(state.last_tick + 1, to_tick + 1):
        # 종목 순회 순서를 고정해야 증분 계산과 일괄 계산이 같은 난수를 소비한다.
        for symbol, stock in config.STOCKS.items():
            state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
            # 적정가까지 남은 로그거리에 비례해 당긴다(Ornstein-Uhlenbeck).
            # 난수를 쓰지 않으므로 증분/일괄 동일성은 그대로다.
            gap = state.anchor_log[symbol] - state.log_return[symbol]
            state.log_return[symbol] += config.ANCHOR_PULL * gap
        for plan in active:
            if plan.publish_tick < tick <= plan.publish_tick + plan.ramp_seconds:
                state.log_return[plan.symbol] += plan.impact / plan.ramp_seconds
    state.last_tick = max(state.last_tick, to_tick)
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/engine.py app/config.py tests/test_engine.py
git commit -m "feat: 가격을 적정가로 끌어당기는 평균회귀 항

Ornstein-Uhlenbeck 회귀. gap 이 적정가까지 남은 로그거리이므로 힘은
항상 적정가 쪽이고 가까워질수록 약해진다 — 지나치지 않는다.

난수를 쓰지 않으므로 증분 계산과 일괄 계산이 같다는 기존 불변식이
그대로다. 테스트로 다시 못박는다.

앵커는 뉴스보다 약하다. 이기면 뉴스가 장식이 되고 AI 분석 5회의
희소성이 무너진다. 램프가 끝난 뒤 되돌리는 것까지가 의도다."
```

---

### Task 5: 기업분석 횟수와 라운드 재앵커

**Files:**
- Modify: `backend/app/session.py`
- Modify: `backend/tests/test_session_rules.py`

**Interfaces:**
- Consumes: `engine.reanchor`, `fundamentals.fair_values` (Task 1, 3)
- Produces:
  - `GameSession.company_analyses_left: int`
  - `GameSession.analyzed_symbols: set[str]`
  - `session.spend_company_analysis(sess, symbol: str, now: float) -> bool` — 새로 지불했으면 `True`, 이미 이 라운드에 산 종목이면 `False`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_session_rules.py` 끝에 추가한다. 이 파일이 세션을 만드는 방식(헬퍼 이름)은 파일 상단을 보고 맞춘다:

```python
def test_company_analysis_starts_at_the_configured_count(sess_factory):
    sess = sess_factory()
    assert sess.company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND


def test_spending_a_company_analysis_decrements_and_records(sess_factory):
    sess = sess_factory()
    charged = rules.spend_company_analysis(sess, "geno", now=0.0)
    assert charged is True
    assert sess.company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND - 1
    assert "geno" in sess.analyzed_symbols


def test_reanalyzing_the_same_symbol_is_free(sess_factory):
    """재무는 라운드 내내 안 바뀐다. 같은 값을 두 번 팔면 함정이다."""
    sess = sess_factory()
    rules.spend_company_analysis(sess, "geno", now=0.0)
    left = sess.company_analyses_left

    charged = rules.spend_company_analysis(sess, "geno", now=0.0)
    assert charged is False
    assert sess.company_analyses_left == left


def test_company_analysis_runs_out(sess_factory):
    sess = sess_factory()
    for symbol in list(config.STOCKS)[: config.COMPANY_ANALYSES_PER_ROUND]:
        rules.spend_company_analysis(sess, symbol, now=0.0)

    remaining = [s for s in config.STOCKS if s not in sess.analyzed_symbols][0]
    with pytest.raises(TradeError) as caught:
        rules.spend_company_analysis(sess, remaining, now=0.0)
    assert caught.value.code == "no_company_analyses_left"


def test_company_analysis_rejects_unknown_symbol(sess_factory):
    sess = sess_factory()
    with pytest.raises(TradeError) as caught:
        rules.spend_company_analysis(sess, "nope", now=0.0)
    assert caught.value.code == "unknown_symbol"


def test_company_analysis_is_blocked_while_grinding(sess_factory):
    sess = sess_factory()
    sess.cash = 0
    sess.holdings.clear()
    rules.start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as caught:
        rules.spend_company_analysis(sess, "geno", now=1.0)
    assert caught.value.code == "locked"


def test_advance_round_refills_company_analyses_and_clears_symbols(sess_factory):
    sess = sess_factory()
    rules.spend_company_analysis(sess, "geno", now=0.0)
    sess.cash = sess.target

    rules.advance_round(sess)

    assert sess.company_analyses_left == config.COMPANY_ANALYSES_PER_ROUND
    assert sess.analyzed_symbols == set()


def test_advance_round_reanchors_to_the_new_quarter(sess_factory):
    """라운드 2 는 2분기 실적을 본다. 적정가가 움직여야 한다."""
    sess = sess_factory()
    before = dict(sess.prices.anchor_log)
    sess.cash = sess.target

    rules.advance_round(sess)

    assert sess.prices.anchor_log != before
    expected = fundamentals.fair_values(2)
    for symbol in config.STOCKS:
        implied = sess.prices.start_price[symbol] * math.exp(
            sess.prices.anchor_log[symbol]
        )
        assert implied == pytest.approx(expected[symbol], rel=1e-9)


def test_advance_round_does_not_move_prices(sess_factory):
    sess = sess_factory()
    before = {s: engine.price_of(sess.prices, s) for s in config.STOCKS}
    sess.cash = sess.target

    rules.advance_round(sess)

    assert {s: engine.price_of(sess.prices, s) for s in config.STOCKS} == before
```

상단 임포트에 `math`, `pytest`, `from app import config, engine, fundamentals`, `from app.session import TradeError` 가 없으면 추가한다. 이 파일에 세션 팩토리 픽스처가 없으면 기존 테스트가 쓰는 방식 그대로 로컬 헬퍼를 만든다.

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_session_rules.py -q -k company`
Expected: FAIL — `AttributeError: 'GameSession' object has no attribute 'company_analyses_left'`

- [ ] **Step 3: `GameSession` 에 필드 둘을 추가한다**

`analyses_left` 아래:

```python
    company_analyses_left: int = config.COMPANY_ANALYSES_PER_ROUND
    analyzed_symbols: set[str] = field(default_factory=set)
```

- [ ] **Step 4: `spend_company_analysis` 를 추가한다**

`spend_analysis` 바로 아래:

```python
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
```

- [ ] **Step 5: `advance_round` 가 리필하고 재앵커한다**

```python
def advance_round(sess: GameSession) -> None:
    current = equity(sess)
    sess.round_no += 1
    sess.round_start_equity = current
    sess.target = current * config.ROUND_TARGET_MULTIPLIER
    sess.analyses_left = config.ANALYSES_PER_ROUND
    sess.company_analyses_left = config.COMPANY_ANALYSES_PER_ROUND
    sess.analyzed_symbols.clear()
    sess.grind_count = 0
    # 새 분기 실적이 적정가를 옮긴다. 지난 라운드에 산 정보가 낡는다.
    # 가격은 건드리지 않는다 — 점프하면 보유 종목 평가액이 순간이동한다.
    engine.reanchor(sess.prices, fundamentals.fair_values(sess.round_no))
```

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 7: 커밋**

```bash
cd backend
git add app/session.py tests/test_session_rules.py
git commit -m "feat: 기업분석 횟수와 라운드 전환의 재앵커

같은 종목을 다시 분석하면 공짜다. 재무는 라운드 내내 바뀌지 않으므로
같은 값을 두 번 파는 것은 그냥 함정이다.

라운드가 넘어가면 새 분기 실적이 적정가를 옮긴다. 지난 라운드에 산
정보가 낡는다 — 라운드 전환에 지금까지 없던 의미가 생긴다."
```

---

### Task 6: 폴백 해설과 Claude 어댑터

**Files:**
- Modify: `backend/app/fallback.py`
- Create: `backend/app/company_analysis.py`
- Create: `backend/tests/test_company_analysis.py`

**Interfaces:**
- Consumes: `fundamentals.VALUATION_LABELS`, `fundamentals.valuation_of` (Task 1)
- Produces:
  - `fallback.write_company_commentary(name: str, sector: str, valuation: str, gap: float, financials: dict) -> str`
  - `company_analysis.fetch_commentary(name: str, sector: str, valuation: str, gap: float, financials: dict, client) -> tuple[str, bool]`
  - `company_analysis.build_company_prompt(...) -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_company_analysis.py`:

```python
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
        text = _commentary(valuation=valuation)
        assert text.strip()


def test_fallback_names_the_verdict():
    text = _commentary(valuation="overvalued")
    assert fundamentals.VALUATION_LABELS["overvalued"] in text


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


def test_prompt_never_invites_a_reverdict():
    system = company_analysis.SYSTEM
    assert "다시 판단" in system or "뒤집지" in system
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_company_analysis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.company_analysis'`

- [ ] **Step 3: `fallback.py` 에 템플릿 해설을 추가한다**

`_COMMENTARY` 아래에 붙인다:

```python
_VALUATION_COMMENTARY = {
    "severely_overvalued": "{name} 의 현재가는 {sector} 섹터 기준 배수로 설명되지 않는 수준이다. 판정: {label}. 괴리는 {gap:+.1f}% 다.",
    "overvalued": "{name} 은 {sector} 섹터 기준 배수를 웃돈다. 판정: {label}. 괴리는 {gap:+.1f}% 로, 재료가 식으면 되돌림이 나온다.",
    "fair": "{name} 의 현재가는 {sector} 섹터 기준 배수에 부합한다. 판정: {label}. 괴리는 {gap:+.1f}% 다. 여기서는 뉴스가 방향을 정한다.",
    "undervalued": "{name} 은 {sector} 섹터 기준 배수를 밑돈다. 판정: {label}. 괴리는 {gap:+.1f}% 로, 재료 없이도 되돌아올 여지가 있다.",
    "severely_undervalued": "{name} 의 현재가는 {sector} 섹터 기준 배수와 크게 벌어져 있다. 판정: {label}. 괴리는 {gap:+.1f}% 다.",
}


def write_company_commentary(
    name: str, sector: str, valuation: str, gap: float, financials: dict
) -> str:
    """확정된 밸류에이션 등급을 사람 말로 옮긴다. 판정은 여기서 다시 하지 않는다."""
    from app import fundamentals

    head = _VALUATION_COMMENTARY[valuation].format(
        name=name, sector=sector, gap=gap,
        label=fundamentals.VALUATION_LABELS[valuation],
    )
    if financials.get("per") is None:
        tail = " 이번 분기는 적자라 이익 기준 배수가 성립하지 않아 매출 기준으로 봤다."
    else:
        tail = f" 현재 PER 은 {financials['per']}배, 부채비율은 {financials['debt_ratio']}% 다."
    return head + tail
```

> `fundamentals` 를 함수 안에서 임포트하는 이유: `fundamentals` 가 `config` 를, `fallback` 도 `config` 를 임포트한다. 모듈 최상단에서 서로를 부르면 순환이 생길 수 있어 호출 시점으로 미룬다.

- [ ] **Step 4: `app/company_analysis.py` 를 쓴다**

```python
"""기업분석 해설을 확보한다. Claude 를 아는 세 번째 파일.

analysis.py 와 같은 규칙이다 — 판정은 서버가 확정하고 Claude 는 근거만
설명한다. Claude 가 다시 판정하면 플레이어에게 보이는 등급과 앵커가
실제로 끌어당기는 방향이 어긋난다.
"""
import logging

from pydantic import BaseModel

from app import config, fallback, fundamentals

log = logging.getLogger(__name__)

SYSTEM = """당신은 증권사 애널리스트입니다.
기업의 분기 재무와 확정된 밸류에이션 판정을 받고, 그 판정이 왜 그런지를 수치를 근거로 설명합니다.

규칙:
- 판정은 이미 정해져 있습니다. 다시 판단하거나 뒤집지 않습니다.
- 주어진 수치만 근거로 삼습니다. 없는 수치를 지어내지 않습니다.
- 2~3문장, 건조한 애널리스트 어투로 씁니다.
- 목표주가나 투자 권유 표현은 쓰지 않습니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·기관의 이름을 쓰지 않습니다."""


class Commentary(BaseModel):
    commentary: str


def build_company_prompt(
    name: str, sector: str, valuation: str, gap: float, financials: dict
) -> str:
    """확정된 등급과 재무를 전부 넘긴다. 적정가 자체는 넘기지 않는다 —
    Claude 가 문장에 숫자를 흘리면 등급만 사려던 플레이어가 덤을 받는다."""
    per = financials["per"]
    per_line = f"{per}배" if per is not None else "적자로 산출 불가"
    return (
        f"회사: {name} ({sector})\n"
        f"분기: {financials['quarter']}\n"
        f"매출액: {financials['revenue']:,}원\n"
        f"영업이익: {financials['operating_income']:,}원\n"
        f"당기순이익: {financials['net_income']:,}원\n"
        f"EPS: {financials['eps']:,}원\n"
        f"PER: {per_line}\n"
        f"부채비율: {financials['debt_ratio']}%\n\n"
        f"확정된 판정: {fundamentals.VALUATION_LABELS[valuation]} "
        f"(섹터 기준 배수 대비 {gap:+.1f}%)\n\n"
        "이 판정의 근거를 위 수치에서 찾아 설명해 주세요."
    )


def fetch_commentary(
    name: str, sector: str, valuation: str, gap: float, financials: dict, client
) -> tuple[str, bool]:
    """(해설, offline 여부). 어떤 실패든 로컬 문장으로 떨어진다."""
    def _local() -> tuple[str, bool]:
        return fallback.write_company_commentary(
            name, sector, valuation, gap, financials
        ), True

    if client is None:
        return _local()

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": build_company_prompt(name, sector, valuation, gap, financials),
            }],
            thinking={"type": "adaptive"},
            output_config={"effort": config.ANALYSIS_EFFORT},
            output_format=Commentary,
        )
    except Exception:
        log.warning("기업분석 해설 호출 실패 — 로컬 문장으로 대체합니다.", exc_info=True)
        return _local()

    if getattr(response, "stop_reason", None) == "refusal":
        log.warning("기업분석 해설을 거절했습니다 — 로컬 문장으로 대체합니다.")
        return _local()

    parsed = response.parsed_output
    if parsed is None or not parsed.commentary.strip():
        log.warning("빈 기업분석 해설이 돌아왔습니다 — 로컬 문장으로 대체합니다.")
        return _local()

    return parsed.commentary, False
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/fallback.py app/company_analysis.py tests/test_company_analysis.py
git commit -m "feat: 기업분석 해설 — Claude 어댑터와 로컬 폴백

analysis.py 와 같은 규칙이다. 판정은 서버가 확정하고 Claude 는 근거만
설명한다 — 다시 판정하면 플레이어가 보는 등급과 앵커가 실제로 끌어당기는
방향이 어긋난다.

프롬프트에 적정가 자체는 넣지 않는다. 문장에 숫자가 흘러나오면 등급만
사려던 플레이어가 덤을 받는다.

실패 경로 다섯 개(키 없음·예외·거절·빈 응답·정상)를 전부 테스트한다."
```

---

### Task 7: HTTP 엔드포인트

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: 앞의 전부
- Produces: `POST /api/company-analysis`, 스냅샷의 `company_analyses_left` 와 `stocks[].fundamentals_analyzed`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_api.py` 끝에 추가한다. **이 파일의 기존 헬퍼를 쓴다** — 게임 시작은 `start(client, ELAPSED)`, 상태 조회는 `state(client, sid)` 이고 `client` 는 픽스처다. `client.post("/api/game")` 을 직접 부르지 않는다:

```python
def test_snapshot_reports_company_analyses_left(client):
    snapshot = start(client, ELAPSED)
    assert snapshot["company_analyses_left"] == config.COMPANY_ANALYSES_PER_ROUND
    assert all(row["fundamentals_analyzed"] is False for row in snapshot["stocks"])


def test_snapshot_never_leaks_fair_value(client):
    """적정가가 스냅샷에 실리면 F12 한 번으로 기업분석이 무의미해진다."""
    snapshot = start(client, ELAPSED)
    raw = json.dumps(snapshot, ensure_ascii=False)
    assert "fair_value" not in raw
    assert "valuation" not in raw
    for row in snapshot["stocks"]:
        assert "fair_value" not in row
        assert "valuation" not in row


def test_company_analysis_returns_the_verdict(client):
    session_id = start(client, ELAPSED)["session_id"]
    body = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": "geno"}
    ).json()

    assert body["symbol"] == "geno"
    assert body["name"] == config.STOCKS["geno"].name
    assert body["fair_value"] > 0
    assert body["valuation"] in fundamentals.VALUATION_LABELS
    assert body["label"] == fundamentals.VALUATION_LABELS[body["valuation"]]
    assert body["commentary"].strip()
    assert body["company_analyses_left"] == config.COMPANY_ANALYSES_PER_ROUND - 1
    assert body["financials"]["quarter"] == "2024Q1"


def test_company_analysis_verdict_matches_the_prices(client):
    """등급이 실제 가격·적정가와 어긋나면 앵커와 모순된다."""
    session_id = start(client, ELAPSED)["session_id"]
    body = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": "geno"}
    ).json()

    expected_gap = fundamentals.gap_pct(body["current_price"], body["fair_value"])
    assert body["gap_pct"] == expected_gap
    assert body["valuation"] == fundamentals.valuation_of(expected_gap)


def test_company_analysis_marks_the_stock_in_the_snapshot(client):
    session_id = start(client, ELAPSED)["session_id"]
    client.post("/api/company-analysis", json={"session_id": session_id, "symbol": "geno"})

    rows = {row["symbol"]: row for row in state(client, session_id)["stocks"]}
    assert rows["geno"]["fundamentals_analyzed"] is True
    assert rows["hanbit"]["fundamentals_analyzed"] is False


def test_company_analysis_is_free_the_second_time(client):
    session_id = start(client, ELAPSED)["session_id"]
    first = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": "geno"}
    ).json()
    second = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": "geno"}
    ).json()
    assert second["company_analyses_left"] == first["company_analyses_left"]
    assert second["fair_value"] == first["fair_value"]


def test_company_analysis_runs_out(client):
    session_id = start(client, ELAPSED)["session_id"]
    for symbol in list(config.STOCKS)[: config.COMPANY_ANALYSES_PER_ROUND]:
        client.post(
            "/api/company-analysis", json={"session_id": session_id, "symbol": symbol}
        )
    remaining = list(config.STOCKS)[config.COMPANY_ANALYSES_PER_ROUND]

    response = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": remaining}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "no_company_analyses_left"


def test_company_analysis_rejects_unknown_symbol(client):
    session_id = start(client, ELAPSED)["session_id"]
    response = client.post(
        "/api/company-analysis", json={"session_id": session_id, "symbol": "nope"}
    )
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

    response = client.post(
        "/api/company-analysis", json={"session_id": sid, "symbol": "geno"}
    )

    assert response.status_code == 200
    assert observed["locked"] is False, "기업분석 호출 중 세션 락이 잡혀 있다"
    assert response.json()["commentary"].strip()


def test_company_analysis_rejects_a_dead_session(client):
    response = client.post(
        "/api/company-analysis", json={"session_id": "없는세션", "symbol": "geno"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_session"
```

`import json`, `from app import config, fundamentals` 가 상단에 없으면 추가한다.

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -q -k company`
Expected: FAIL — 404. 라우트가 없다.

- [ ] **Step 3: 스냅샷에 두 필드를 넣는다**

`main.py` 상단 임포트에 `company_analysis` 와 `fundamentals` 를 더한다:

```python
from app import (
    analysis, company_analysis, config, engine, fallback, fundamentals,
    news, session as rules,
)
```

`_stock_rows` 에 한 줄:

```python
            "held": sess.holdings.get(symbol, 0),
            "fundamentals_analyzed": symbol in sess.analyzed_symbols,
```

`_snapshot` 에 한 줄 (`analyses_left` 아래):

```python
        "analyses_left": sess.analyses_left,
        "company_analyses_left": sess.company_analyses_left,
```

- [ ] **Step 4: 요청 본문과 라우트를 추가한다**

`AnalyzeBody` 아래:

```python
class CompanyAnalyzeBody(SessionBody):
    symbol: str
```

`analyze` 라우트 아래에 새 라우트를 넣는다:

```python
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
        stock = config.STOCKS[body.symbol]
        quarter = fundamentals.quarter_of(
            fundamentals.load(), body.symbol, sess.round_no
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
```

> **왜 판정을 락 안에서 확정하나:** `analyze` 는 해설이 끝난 뒤 남은 램프를 **다시 잰다** — 램프는 시간에 따라 닳는 자원이라 기다린 만큼 줄어드는 것이 맞기 때문이다. 적정가는 반대로 라운드 내내 고정이므로 다시 잴 것이 없고, 지불 시점에 확정해 두는 편이 맞다. 락 밖에서 읽으면 그 사이 다른 요청이 tick 을 밀어 `current_price` 와 `gap_pct` 가 서로 다른 순간을 가리킬 수 있다. **락은 여기까지고, Claude 호출은 여전히 락 밖이다.**

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 서버를 실제로 띄워 한 판 확인한다**

```bash
cd backend
./run.sh &
sleep 3
SID=$(curl -s -X POST localhost:7999/api/game | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -s -X POST localhost:7999/api/company-analysis \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"symbol\":\"geno\"}" | python3 -m json.tool
kill %1
```

Expected: `fair_value`, `valuation`, `commentary`, `company_analyses_left: 1` 이 들어있는 JSON. 키가 없으면 `offline: true`.

- [ ] **Step 7: 커밋**

```bash
cd backend
git add app/main.py tests/test_api.py
git commit -m "feat: HTTP — 기업분석 엔드포인트와 스냅샷 2필드

analyze 와 같은 락 패턴이다. 차감까지만 락 안에서 하고 Claude 호출은
락 밖에서 기다린다 — 락을 쥔 채 기다리면 같은 세션의 폴링이 멈춰
시장이 얼어붙는다.

판정은 지불 시점의 가격 기준이다. 남은 램프를 다시 재는 analyze 와
반대인데, 램프는 시간에 닳는 자원이고 적정가는 라운드 내내 고정이라
그렇다.

스냅샷에 fair_value 와 valuation 이 없다는 것을 테스트가 못박는다."
```

---

## 마무리

- [ ] **전체 테스트**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 122개 + 새로 추가된 것들.

- [ ] **README 의 현재 상태를 갱신한다**

`README.md` 의 모듈 표에 `fundamentals` 와 `company_analysis` 를 더하고, 테스트 개수와 "현재 상태" 절을 실제 숫자로 고친다. **세어 보고 쓴다.**

- [ ] **`docs/api.md` 3부를 1부로 승격한다**

3부가 구현되었으므로 §14~§17 의 내용을 1부 형식(실제 응답 캡처)으로 옮긴다. 실제 서버를 띄워 응답을 캡처해서 쓴다 — 추정으로 쓰지 않는다. 이것이 이 문서의 규약이다.

- [ ] **푸시하고 `main` 으로 합칠지 결정한다**

`superpowers:finishing-a-development-branch` 를 쓴다.
