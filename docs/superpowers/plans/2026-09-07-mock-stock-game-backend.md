# 모의주식게임 백엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 생성 뉴스로 움직이는 가상 주식시장의 서버 측 전부를 만든다 — 가격 엔진, 낚시 뉴스 시나리오, 매매·파산·노가다·라운드 규칙, Claude 연동과 로컬 폴백, HTTP API. 완료 시 브라우저 없이 `curl`과 테스트만으로 한 판을 끝까지 플레이할 수 있다.

**Architecture:** 서버 권위 + 폴링. FastAPI가 세션 상태와 뉴스의 진짜 임팩트를 메모리에 들고, 클라이언트는 가격만 받는다. 백그라운드 타이머를 돌리지 않고 `GET /api/state` 요청이 올 때 마지막 계산 tick부터 현재 tick까지만 이어서 계산한다(증분 lazy 계산). 밸런스 수치는 코드가 확정하고 Claude는 문장만 쓴다.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, Pydantic v2, `anthropic` SDK, pytest. 프론트엔드는 이 계획의 범위가 아니다.

**Spec:** `docs/superpowers/specs/2026-09-07-mock-stock-game-design.md`

## Global Constraints

이 절의 요구사항은 모든 태스크에 암묵적으로 포함된다.

**설정값** — 전부 `app/config.py`가 소유한다. 다른 파일에 숫자 리터럴을 두지 않는다.

| 이름 | 값 |
|---|---|
| `SEED_CASH` | `1_000_000` |
| `ROUND_TARGET_MULTIPLIER` | `3` |
| `TRADE_FEE_RATE` | `0.002` |
| `BANKRUPTCY_THRESHOLD` | `100_000` |
| `ANALYSES_PER_ROUND` | `5` |
| `GRIND_LOCK_SECONDS` | `120` |
| `GRIND_BASE_PAYOUT` | `200_000` |
| `GRIND_DECAY_NUM` / `GRIND_DECAY_DEN` | `3` / `5` (= 0.6, 정수 나눗셈으로 계산해 부동소수점 오차를 없앤다) |
| `TICK_SECONDS` | `1` |
| `NEWS_INTERVAL_RANGE` | `(12, 18)` |
| `NEWS_BATCH_SIZE` | `20` |
| `NEWS_FIRST_WAIT_COUNT` | `5` |
| `NEWS_REFILL_THRESHOLD` | `5` |
| `IMPACT_HONEST` | `(0.05, 0.15)` |
| `IMPACT_EXAGGERATED` | `(0.00, 0.015)` |
| `IMPACT_REVERSED` | `(0.06, 0.12)` |
| `RAMP_SECONDS_RANGE` | `(15, 40)` |
| `STRENGTH_STRONG_MIN` | `0.08` |
| `STRENGTH_WEAK_MIN` | `0.02` |
| `HONEST_RATIO_START` | `0.60` |
| `HONEST_RATIO_STEP` | `0.10` |
| `HONEST_RATIO_FLOOR` | `0.30` |
| `MODEL` | `"claude-opus-5"` |
| `NEWS_EFFORT` | `"medium"` |
| `ANALYSIS_EFFORT` | `"low"` |

**종목 6개** — 시작가와 tick당 변동성.

| 심볼 키 | 종목명 | 섹터 | 시작가 | 변동성 |
|---|---|---|---|---|
| `hanbit` | 한빛솔리드 | 반도체 | `82_000` | `0.0030` |
| `geno` | 제노셀 | 바이오 | `45_000` | `0.0040` |
| `sungjin` | 성진셀즈 | 2차전지 | `61_000` | `0.0030` |
| `pixel` | 픽셀로그 | 게임 | `33_000` | `0.0025` |
| `taesan` | 태산건영 | 건설 | `18_500` | `0.0015` |
| `arawings` | 아라윙스 | 항공 | `24_000` | `0.0020` |

**돈은 정수** — 수량은 주식 수(int), 현금은 원 단위(int). 가격만 float으로 계산하되 외부로 나가는 순간 `math.floor`로 내린다. **반올림은 전 구간 내림 하나로 통일한다.** 방향이 섞이면 총자산이 몇 원씩 어긋나 파산 판정이 흔들린다.

**시간과 난수는 주입한다** — `engine`과 `session`의 어떤 함수도 `time.monotonic()`이나 모듈 전역 `random`을 직접 부르지 않는다. 현재 시각은 `now: float` 인자로 받고, 난수는 세션이 소유한 `random.Random` 인스턴스를 받는다. 이것이 120초 노가다를 `sleep` 없이 테스트하고 수천 tick 뒤 상태를 즉시 만드는 유일한 방법이다.

**정답은 서버에만 둔다** — `NewsPlan.impact`, `NewsPlan.kind`는 어떤 응답에도 실어 보내지 않는다. 클라이언트로 나가는 것은 가격, 그리고 분석을 쓴 뒤의 등급뿐이다.

**Claude는 판정자가 아니라 해설자다** — 임팩트와 램프는 `scenario.py`가 확정한다. Claude는 (1) 뉴스 문장을 쓰고 (2) 확정된 판정을 해설로 풀어쓴다. Claude 응답으로 임팩트나 등급을 다시 정하지 않는다.

**테스트는 Claude를 한 번도 부르지 않는다** — 전부 가짜 클라이언트를 주입한다. `ANTHROPIC_API_KEY` 없이 `pytest`가 전부 통과해야 한다.

---

## File Structure

| 파일 | 책임 | 아는 것 | 모르는 것 |
|---|---|---|---|
| `app/config.py` | 모든 밸런스 수치와 종목표 | 없음 | 전부 |
| `app/models.py` | 도메인 dataclass와 API Pydantic 스키마 | 자료 형태 | 로직 |
| `app/scenario.py` | 라운드+시드 → 시나리오 배분표 | 밸런스 규칙 | Claude, HTTP, 가격 |
| `app/engine.py` | 상태+목표 tick → 로그가격 증분 진행 | 램프, 노이즈 | Claude, HTTP, 세션 |
| `app/session.py` | 매매·수수료·파산·노가다·라운드·분석 차감 | 도메인 규칙 | Claude, HTTP |
| `app/fallback.py` | 템플릿 뉴스 생성, 등급 → 해설 문장 | 문장 템플릿 | Claude, HTTP |
| `app/news.py` | 뉴스 문장 확보 (Claude → 실패 시 fallback) | Claude, fallback | 게임 규칙 |
| `app/analysis.py` | 분석 해설 확보 (Claude → 실패 시 fallback) | Claude, fallback | 게임 규칙 |
| `app/main.py` | FastAPI 라우트, 세션 저장소, 세션별 락 | HTTP, 상태 코드 | 계산 로직 |

태스크 순서는 의존 방향과 같다: `config`/`models` → `scenario` → `engine` → `session` → `fallback` → Claude 어댑터 → `main`.

---

### Task 1: 설정과 시나리오 배분표

낚시 뉴스의 밸런스를 코드가 소유한다는 원칙이 여기서 구현된다. 순수 함수라 Claude도 HTTP도 모른다.

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py` (빈 파일)
- Create: `app/config.py`
- Create: `app/models.py`
- Create: `app/scenario.py`
- Test: `tests/test_scenario.py`
- Create: `tests/__init__.py` (빈 파일)

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `config.STOCKS: dict[str, Stock]` — 키는 심볼, `Stock`은 `name`/`sector`/`base_price`/`volatility`
  - `models.NewsPlan` — frozen dataclass, 필드 `news_id: int`, `symbol: str`, `surface_tone: str`, `kind: str`, `impact: float`, `ramp_seconds: int`, `publish_tick: int`
  - `scenario.honest_ratio(round_no: int) -> float`
  - `scenario.allocate(total: int, round_no: int) -> dict[str, int]` — 키 `"honest"`, `"exaggerated"`, `"reversed"`
  - `scenario.build_plans(total: int, round_no: int, rng: random.Random, first_news_id: int, first_tick: int) -> list[NewsPlan]`

- [ ] **Step 1: 의존성과 패키지 골격을 만든다**

`requirements.txt`:

```
fastapi==0.115.6
uvicorn==0.34.0
pydantic==2.10.4
anthropic>=1.0.0
pytest==8.3.4
# fastapi.testclient.TestClient 는 httpx 를 쓴다
httpx==0.28.1
# anthropic SDK 는 httpx 가 아니라 httpx2 위에 있다 (anthropic 이 전이 의존성으로
# 끌어오지만, 버전이 바뀌어도 깨지지 않게 명시해 둔다)
httpx2
```

빈 파일 두 개를 만든다:

```bash
mkdir -p app tests
touch app/__init__.py tests/__init__.py
```

설치:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

이후 모든 명령은 `.venv/bin/python`, `.venv/bin/pytest`를 쓴다.

- [ ] **Step 2: 설정 파일을 쓴다**

`app/config.py`:

```python
"""모든 밸런스 수치. 다른 파일에 숫자 리터럴을 두지 않는다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stock:
    name: str
    sector: str
    base_price: int
    volatility: float  # tick당 로그수익 표준편차


STOCKS: dict[str, Stock] = {
    "hanbit":   Stock("한빛솔리드", "반도체",  82_000, 0.0030),
    "geno":     Stock("제노셀",     "바이오",  45_000, 0.0040),
    "sungjin":  Stock("성진셀즈",   "2차전지", 61_000, 0.0030),
    "pixel":    Stock("픽셀로그",   "게임",    33_000, 0.0025),
    "taesan":   Stock("태산건영",   "건설",    18_500, 0.0015),
    "arawings": Stock("아라윙스",   "항공",    24_000, 0.0020),
}

SEED_CASH = 1_000_000
ROUND_TARGET_MULTIPLIER = 3
TRADE_FEE_RATE = 0.002
BANKRUPTCY_THRESHOLD = 100_000

ANALYSES_PER_ROUND = 5

GRIND_LOCK_SECONDS = 120
GRIND_BASE_PAYOUT = 200_000
# 0.6 을 3/5 로 둔다. 200_000 * 0.6 ** 3 은 43199.99... 가 되어 4회차 보수가
# 43,200 이 아니라 43,199 로 어긋난다. 정수 나눗셈으로 계산한다.
GRIND_DECAY_NUM = 3
GRIND_DECAY_DEN = 5

TICK_SECONDS = 1

NEWS_INTERVAL_RANGE = (12, 18)
NEWS_BATCH_SIZE = 20
NEWS_FIRST_WAIT_COUNT = 5
NEWS_REFILL_THRESHOLD = 5

# 정직 비율: 라운드마다 STEP 만큼 내려가고 FLOOR 아래로는 내려가지 않는다.
# 결과 수열 0.60 / 0.50 / 0.40 / 0.30 / 0.30 ... (스펙의 표와 하한을 함께 만족)
HONEST_RATIO_START = 0.60
HONEST_RATIO_STEP = 0.10
HONEST_RATIO_FLOOR = 0.30

# 정직이 아닌 몫을 과장 : 역방향 = 5 : 3 으로 쪼갠다.
EXAGGERATED_SHARE = 5
REVERSED_SHARE = 3

IMPACT_HONEST = (0.05, 0.15)
IMPACT_EXAGGERATED = (0.00, 0.015)
IMPACT_REVERSED = (0.06, 0.12)

# kind 로 조회하는 형태가 실제 코드가 쓰는 모양이다. 값의 출처는 위 세 상수 하나뿐이다.
IMPACT_RANGES: dict[str, tuple[float, float]] = {
    "honest": IMPACT_HONEST,
    "exaggerated": IMPACT_EXAGGERATED,
    "reversed": IMPACT_REVERSED,
}
RAMP_SECONDS_RANGE = (15, 40)

STRENGTH_STRONG_MIN = 0.08
STRENGTH_WEAK_MIN = 0.02

MODEL = "claude-opus-5"
NEWS_EFFORT = "medium"
ANALYSIS_EFFORT = "low"
```

- [ ] **Step 3: 도메인 자료형을 쓴다**

`app/models.py`:

```python
"""도메인 dataclass. 로직은 담지 않는다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NewsPlan:
    """뉴스 한 건의 확정된 진실. impact 와 kind 는 절대 클라이언트로 내보내지 않는다."""
    news_id: int
    symbol: str
    surface_tone: str   # "positive" | "negative" — 플레이어가 읽는 톤
    kind: str           # "honest" | "exaggerated" | "reversed"
    impact: float       # 로그수익 총량, 부호 포함
    ramp_seconds: int
    publish_tick: int


@dataclass
class NewsItem:
    """문장이 채워진 뉴스."""
    plan: NewsPlan
    headline: str
    body: str
    analyzed: bool = False
    commentary: str = ""
    offline: bool = False   # 폴백으로 만들어졌으면 True
```

- [ ] **Step 4: 실패하는 테스트를 쓴다**

`tests/test_scenario.py`:

```python
import random

import pytest

from app import config
from app.scenario import allocate, build_plans, honest_ratio


def test_honest_ratio_descends_then_holds_at_floor():
    assert honest_ratio(1) == pytest.approx(0.60)
    assert honest_ratio(2) == pytest.approx(0.50)
    assert honest_ratio(3) == pytest.approx(0.40)
    assert honest_ratio(4) == pytest.approx(0.30)
    assert honest_ratio(9) == pytest.approx(0.30)


def test_round_one_allocation_is_twelve_five_three():
    assert allocate(20, 1) == {"honest": 12, "exaggerated": 5, "reversed": 3}


def test_allocation_always_sums_to_total():
    for round_no in range(1, 8):
        for total in (5, 12, 20, 33):
            counts = allocate(total, round_no)
            assert sum(counts.values()) == total


def test_non_honest_share_splits_five_to_three():
    counts = allocate(20, 3)          # 정직 8, 나머지 12
    assert counts["honest"] == 8
    assert counts["exaggerated"] == 8   # round(12 * 5/8) == 8 (7.5 -> 8)
    assert counts["reversed"] == 4


def test_reversed_impact_opposes_its_surface_tone():
    plans = build_plans(60, 1, random.Random(1), first_news_id=0, first_tick=0)
    reversed_plans = [p for p in plans if p.kind == "reversed"]
    assert reversed_plans, "역방향 뉴스가 생성되지 않았다"
    for p in reversed_plans:
        if p.surface_tone == "positive":
            assert p.impact < 0
        else:
            assert p.impact > 0


def test_honest_impact_agrees_with_its_surface_tone():
    plans = build_plans(60, 1, random.Random(2), first_news_id=0, first_tick=0)
    for p in (p for p in plans if p.kind == "honest"):
        assert (p.impact > 0) == (p.surface_tone == "positive")


def test_exaggerated_impact_is_negligible():
    plans = build_plans(60, 1, random.Random(3), first_news_id=0, first_tick=0)
    exaggerated = [p for p in plans if p.kind == "exaggerated"]
    assert exaggerated
    for p in exaggerated:
        assert abs(p.impact) <= config.IMPACT_RANGES["exaggerated"][1]


def test_same_seed_produces_identical_table():
    a = build_plans(20, 1, random.Random(7), first_news_id=0, first_tick=0)
    b = build_plans(20, 1, random.Random(7), first_news_id=0, first_tick=0)
    assert a == b


def test_publish_ticks_are_increasing_and_within_interval_range():
    plans = build_plans(20, 1, random.Random(11), first_news_id=0, first_tick=100)
    lo, hi = config.NEWS_INTERVAL_RANGE
    ticks = [p.publish_tick for p in plans]
    assert ticks == sorted(ticks)
    assert lo <= ticks[0] - 100 <= hi
    for earlier, later in zip(ticks, ticks[1:]):
        assert lo <= later - earlier <= hi


def test_news_ids_are_sequential_from_the_given_start():
    plans = build_plans(4, 1, random.Random(5), first_news_id=17, first_tick=0)
    assert [p.news_id for p in plans] == [17, 18, 19, 20]


def test_impact_range_constants_and_lookup_table_agree():
    assert config.IMPACT_RANGES == {
        "honest": config.IMPACT_HONEST,
        "exaggerated": config.IMPACT_EXAGGERATED,
        "reversed": config.IMPACT_REVERSED,
    }


def test_every_plan_names_a_real_stock_and_valid_ramp():
    plans = build_plans(40, 1, random.Random(13), first_news_id=0, first_tick=0)
    lo, hi = config.RAMP_SECONDS_RANGE
    for p in plans:
        assert p.symbol in config.STOCKS
        assert lo <= p.ramp_seconds <= hi
        assert p.surface_tone in ("positive", "negative")
        assert p.kind in ("honest", "exaggerated", "reversed")
```

- [ ] **Step 5: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_scenario.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scenario'`

- [ ] **Step 6: 최소 구현을 쓴다**

`app/scenario.py`:

```python
"""라운드와 시드로부터 시나리오 배분표를 만든다. 밸런스 규칙을 소유한다."""
import random

from app import config
from app.models import NewsPlan


def honest_ratio(round_no: int) -> float:
    """라운드가 오를수록 정직 뉴스 비율이 내려가고, 하한에서 멈춘다."""
    ratio = config.HONEST_RATIO_START - config.HONEST_RATIO_STEP * (round_no - 1)
    return max(config.HONEST_RATIO_FLOOR, ratio)


def allocate(total: int, round_no: int) -> dict[str, int]:
    """total 건을 정직/과장/역방향으로 쪼갠다. 합은 항상 total 이다."""
    honest = round(total * honest_ratio(round_no))
    rest = total - honest
    shares = config.EXAGGERATED_SHARE + config.REVERSED_SHARE
    exaggerated = round(rest * config.EXAGGERATED_SHARE / shares)
    return {
        "honest": honest,
        "exaggerated": exaggerated,
        "reversed": rest - exaggerated,
    }


def _impact(kind: str, surface_tone: str, rng: random.Random) -> float:
    lo, hi = config.IMPACT_RANGES[kind]
    magnitude = rng.uniform(lo, hi)
    tone_is_up = surface_tone == "positive"
    # 역방향은 표면 톤과 반대로 움직인다. 그것이 함정의 정의다.
    goes_up = (not tone_is_up) if kind == "reversed" else tone_is_up
    return magnitude if goes_up else -magnitude


def build_plans(
    total: int,
    round_no: int,
    rng: random.Random,
    first_news_id: int,
    first_tick: int,
) -> list[NewsPlan]:
    """확정된 뉴스 계획 목록. 등장 시각까지 여기서 정한다."""
    kinds: list[str] = []
    for kind, count in allocate(total, round_no).items():
        kinds.extend([kind] * count)
    rng.shuffle(kinds)

    symbols = list(config.STOCKS)
    interval_lo, interval_hi = config.NEWS_INTERVAL_RANGE
    ramp_lo, ramp_hi = config.RAMP_SECONDS_RANGE

    plans: list[NewsPlan] = []
    tick = first_tick
    for offset, kind in enumerate(kinds):
        tick += rng.randint(interval_lo, interval_hi)
        surface_tone = rng.choice(("positive", "negative"))
        plans.append(
            NewsPlan(
                news_id=first_news_id + offset,
                symbol=rng.choice(symbols),
                surface_tone=surface_tone,
                kind=kind,
                impact=_impact(kind, surface_tone, rng),
                ramp_seconds=rng.randint(ramp_lo, ramp_hi),
                publish_tick=tick,
            )
        )
    return plans
```

- [ ] **Step 7: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_scenario.py -v`
Expected: PASS — 12 passed

- [ ] **Step 8: 커밋**

```bash
git add requirements.txt app/__init__.py app/config.py app/models.py app/scenario.py tests/__init__.py tests/test_scenario.py
git commit -m "feat: 시나리오 배분표와 밸런스 설정

낚시 뉴스의 임팩트와 램프를 코드가 확정한다. Claude 는 나중에 문장만 채운다."
```

---

### Task 2: 가격 엔진

램프가 가격이 되는 기계 장치. 순수 함수라 세션도 HTTP도 모른다.

**Files:**
- Create: `app/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `config.STOCKS`, `models.NewsPlan` (Task 1)
- Produces:
  - `engine.PriceState` — dataclass, 필드 `log_return: dict[str, float]`, `last_tick: int`
  - `engine.new_state() -> PriceState`
  - `engine.advance(state: PriceState, plans: Sequence[NewsPlan], to_tick: int, rng: random.Random) -> None` — 제자리 변경
  - `engine.price_of(state: PriceState, symbol: str) -> int` — 내림한 정수 원
  - `engine.ramp_progress(plan: NewsPlan, tick: int) -> float` — 0.0~1.0
  - `engine.ramp_remaining(plan: NewsPlan, tick: int) -> int` — 남은 초, 끝났으면 0

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_engine.py`:

```python
import math
import random

import pytest

from app import config
from app.engine import (
    advance,
    new_state,
    price_of,
    ramp_progress,
    ramp_remaining,
)
from app.models import NewsPlan


class ZeroRandom(random.Random):
    """노이즈를 죽여 램프만 남긴다."""

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return 0.0


def plan(symbol="geno", impact=0.10, ramp=20, publish_tick=0, news_id=0):
    return NewsPlan(
        news_id=news_id,
        symbol=symbol,
        surface_tone="positive" if impact > 0 else "negative",
        kind="honest",
        impact=impact,
        ramp_seconds=ramp,
        publish_tick=publish_tick,
    )


def test_no_news_and_no_noise_leaves_price_untouched():
    state = new_state()
    advance(state, [], to_tick=500, rng=ZeroRandom(0))
    for symbol, stock in config.STOCKS.items():
        assert price_of(state, symbol) == stock.base_price


def test_price_at_ramp_end_equals_base_times_exp_impact():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    expected = math.floor(config.STOCKS["geno"].base_price * math.exp(0.10))
    assert price_of(state, "geno") == expected


def test_ramp_stops_contributing_after_it_finishes():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=20, rng=ZeroRandom(0))
    at_end = price_of(state, "geno")
    advance(state, [p], to_tick=400, rng=ZeroRandom(0))
    assert price_of(state, "geno") == at_end


def test_price_midway_through_ramp_is_half_the_impact():
    state = new_state()
    p = plan(impact=0.10, ramp=20, publish_tick=0)
    advance(state, [p], to_tick=10, rng=ZeroRandom(0))
    expected = math.floor(config.STOCKS["geno"].base_price * math.exp(0.05))
    assert price_of(state, "geno") == expected


def test_negative_impact_pushes_price_down():
    state = new_state()
    p = plan(impact=-0.08, ramp=16, publish_tick=0)
    advance(state, [p], to_tick=16, rng=ZeroRandom(0))
    assert price_of(state, "geno") < config.STOCKS["geno"].base_price


def test_news_only_moves_its_own_symbol():
    state = new_state()
    p = plan(symbol="geno", impact=0.12, ramp=15, publish_tick=0)
    advance(state, [p], to_tick=15, rng=ZeroRandom(0))
    for symbol, stock in config.STOCKS.items():
        if symbol != "geno":
            assert price_of(state, symbol) == stock.base_price


def test_incremental_advance_matches_one_big_advance():
    """500ms 폴링이든 탭을 비웠다 돌아오든 같은 가격이 나와야 한다."""
    plans = [plan(impact=0.09, ramp=25, publish_tick=30, news_id=1)]

    stepwise = new_state()
    rng_a = random.Random(42)
    for tick in range(1, 101):
        advance(stepwise, plans, to_tick=tick, rng=rng_a)

    at_once = new_state()
    advance(at_once, plans, to_tick=100, rng=random.Random(42))

    assert stepwise.log_return == at_once.log_return
    assert stepwise.last_tick == at_once.last_tick == 100


def test_advance_to_a_past_tick_is_a_no_op():
    state = new_state()
    advance(state, [], to_tick=50, rng=random.Random(1))
    snapshot = dict(state.log_return)
    advance(state, [], to_tick=20, rng=random.Random(1))
    assert state.log_return == snapshot
    assert state.last_tick == 50


def test_noise_actually_moves_prices():
    state = new_state()
    advance(state, [], to_tick=200, rng=random.Random(3))
    assert any(
        price_of(state, symbol) != stock.base_price
        for symbol, stock in config.STOCKS.items()
    )


def test_base_prices_survive_the_float_round_trip():
    """log(base) 를 저장하면 exp 왕복에서 1원이 사라진다 — 6종목 중 4종목이 그랬다.
    누적 로그수익을 저장하고 정수 시작가에 곱해야 tick 0 가 정확하다."""
    state = new_state()
    for symbol, stock in config.STOCKS.items():
        assert price_of(state, symbol) == stock.base_price


def test_ramp_progress_clamps_to_zero_and_one():
    p = plan(impact=0.10, ramp=20, publish_tick=100)
    assert ramp_progress(p, 90) == pytest.approx(0.0)
    assert ramp_progress(p, 100) == pytest.approx(0.0)
    assert ramp_progress(p, 110) == pytest.approx(0.5)
    assert ramp_progress(p, 120) == pytest.approx(1.0)
    assert ramp_progress(p, 999) == pytest.approx(1.0)


def test_ramp_remaining_counts_down_to_zero():
    p = plan(impact=0.10, ramp=20, publish_tick=100)
    assert ramp_remaining(p, 100) == 20
    assert ramp_remaining(p, 112) == 8
    assert ramp_remaining(p, 120) == 0
    assert ramp_remaining(p, 500) == 0
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine'`

- [ ] **Step 3: 최소 구현을 쓴다**

`app/engine.py`:

```python
"""가격 엔진. 상태와 목표 tick 을 받아 누적 로그수익을 증분으로 진행한다.

백그라운드 타이머를 돌리지 않는다. 요청이 올 때 마지막 계산 tick 부터
현재 tick 까지만 이어서 계산하므로, 500ms 폴링이면 매 요청 0~1 tick 이고
탭을 비웠다 돌아오면 밀린 tick 을 한꺼번에 계산한다.
"""
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from app import config
from app.models import NewsPlan


@dataclass
class PriceState:
    log_return: dict[str, float] = field(default_factory=dict)
    last_tick: int = 0


def new_state() -> PriceState:
    # 로그가격이 아니라 누적 로그수익을 든다. log(base) 를 저장하면 exp 왕복에서
    # 1원이 사라진다(6종목 중 4종목). 정수 시작가는 정확히 남기고 수익률만 float 로 둔다.
    return PriceState(
        log_return={symbol: 0.0 for symbol in config.STOCKS},
        last_tick=0,
    )


def advance(
    state: PriceState,
    plans: Sequence[NewsPlan],
    to_tick: int,
    rng: random.Random,
) -> None:
    """state 를 to_tick 까지 진행한다. to_tick 이 과거면 아무것도 하지 않는다."""
    for tick in range(state.last_tick + 1, to_tick + 1):
        # 종목 순회 순서를 고정해야 증분 계산과 일괄 계산이 같은 난수를 소비한다.
        for symbol, stock in config.STOCKS.items():
            state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
        for plan in plans:
            if plan.publish_tick < tick <= plan.publish_tick + plan.ramp_seconds:
                state.log_return[plan.symbol] += plan.impact / plan.ramp_seconds
    state.last_tick = max(state.last_tick, to_tick)


def price_of(state: PriceState, symbol: str) -> int:
    """원 단위 정수. 내림으로 통일한다."""
    return math.floor(
        config.STOCKS[symbol].base_price * math.exp(state.log_return[symbol])
    )


def ramp_progress(plan: NewsPlan, tick: int) -> float:
    elapsed = tick - plan.publish_tick
    if elapsed <= 0:
        return 0.0
    return min(1.0, elapsed / plan.ramp_seconds)


def ramp_remaining(plan: NewsPlan, tick: int) -> int:
    ends_at = plan.publish_tick + plan.ramp_seconds
    return max(0, ends_at - tick)
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_engine.py -v`
Expected: PASS — 12 passed

- [ ] **Step 5: 커밋**

```bash
git add app/engine.py tests/test_engine.py
git commit -m "feat: 램프 기반 가격 엔진

타이머 없이 요청 시점에 증분 계산한다. 증분 결과가 일괄 계산과
같은지를 테스트로 못박아 폴링 간격과 탭 이탈에 무관하게 만든다."
```

---

### Task 3: 매매와 수수료

**Files:**
- Create: `app/session.py`
- Test: `tests/test_trade.py`

**Interfaces:**
- Consumes: `config` (Task 1), `engine.PriceState`/`price_of` (Task 2)
- Produces:
  - `session.GameSession` — dataclass, 필드는 Step 2 코드 참조
  - `session.new_session(session_id: str, rng: random.Random, started_at: float) -> GameSession`
  - `session.TradeError(code: str, message: str)` — `code`는 `"insufficient_cash"`, `"insufficient_shares"`, `"bad_quantity"`, `"unknown_symbol"`, `"locked"`, `"no_analyses_left"`, `"not_bankrupt"`
  - `session.equity(sess: GameSession) -> int`
  - `session.buy(sess: GameSession, symbol: str, qty: int, now: float) -> dict`
  - `session.sell(sess: GameSession, symbol: str, qty: int, now: float) -> dict`
  - `session.max_affordable(sess: GameSession, symbol: str) -> int`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_trade.py`:

```python
import math
import random

import pytest

from app import config
from app.engine import price_of
from app.session import (
    TradeError,
    buy,
    equity,
    max_affordable,
    new_session,
    sell,
)


def fresh():
    return new_session("s1", random.Random(0), started_at=0.0)


def test_new_session_starts_with_seed_cash_and_no_holdings():
    sess = fresh()
    assert sess.cash == config.SEED_CASH
    assert sess.holdings == {}
    assert equity(sess) == config.SEED_CASH
    assert sess.round_no == 1
    assert sess.target == config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER
    assert sess.analyses_left == config.ANALYSES_PER_ROUND


def test_buy_deducts_gross_plus_fee_and_adds_shares():
    sess = fresh()
    price = price_of(sess.prices, "geno")
    result = buy(sess, "geno", 10, now=0.0)

    gross = price * 10
    fee = math.floor(gross * config.TRADE_FEE_RATE)
    assert result == {"symbol": "geno", "qty": 10, "price": price,
                      "gross": gross, "fee": fee, "side": "buy"}
    assert sess.cash == config.SEED_CASH - gross - fee
    assert sess.holdings == {"geno": 10}


def test_sell_credits_gross_minus_fee_and_removes_shares():
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    cash_after_buy = sess.cash
    price = price_of(sess.prices, "geno")

    sell(sess, "geno", 4, now=0.0)

    gross = price * 4
    fee = math.floor(gross * config.TRADE_FEE_RATE)
    assert sess.cash == cash_after_buy + gross - fee
    assert sess.holdings == {"geno": 6}


def test_selling_the_whole_position_drops_the_symbol():
    sess = fresh()
    buy(sess, "geno", 3, now=0.0)
    sell(sess, "geno", 3, now=0.0)
    assert sess.holdings == {}


def test_fee_is_charged_on_both_sides():
    """수수료가 한쪽만 걸리면 왕복 매매가 손해가 아니게 되어 초단타 연타가 이득이 된다."""
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    sell(sess, "geno", 10, now=0.0)
    assert sess.cash < config.SEED_CASH


def test_buy_beyond_cash_is_rejected_and_changes_nothing():
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "geno", 10_000, now=0.0)
    assert excinfo.value.code == "insufficient_cash"
    assert sess.cash == config.SEED_CASH
    assert sess.holdings == {}


def test_sell_beyond_holdings_is_rejected_and_changes_nothing():
    sess = fresh()
    buy(sess, "geno", 2, now=0.0)
    cash = sess.cash
    with pytest.raises(TradeError) as excinfo:
        sell(sess, "geno", 3, now=0.0)
    assert excinfo.value.code == "insufficient_shares"
    assert sess.holdings == {"geno": 2}
    assert sess.cash == cash


@pytest.mark.parametrize("qty", [0, -1, -50])
def test_non_positive_quantity_is_rejected(qty):
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "geno", qty, now=0.0)
    assert excinfo.value.code == "bad_quantity"


def test_unknown_symbol_is_rejected():
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "notreal", 1, now=0.0)
    assert excinfo.value.code == "unknown_symbol"


def test_max_affordable_accounts_for_the_fee():
    sess = fresh()
    price = price_of(sess.prices, "geno")
    qty = max_affordable(sess, "geno")

    cost = price * qty + math.floor(price * qty * config.TRADE_FEE_RATE)
    assert cost <= sess.cash
    over = price * (qty + 1)
    assert over + math.floor(over * config.TRADE_FEE_RATE) > sess.cash


def test_max_affordable_buy_always_succeeds():
    sess = fresh()
    buy(sess, "geno", max_affordable(sess, "geno"), now=0.0)
    assert sess.cash >= 0


def test_equity_is_cash_plus_floored_valuation():
    sess = fresh()
    buy(sess, "geno", 5, now=0.0)
    buy(sess, "pixel", 3, now=0.0)
    expected = (
        sess.cash
        + price_of(sess.prices, "geno") * 5
        + price_of(sess.prices, "pixel") * 3
    )
    assert equity(sess) == expected
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_trade.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.session'`

- [ ] **Step 3: 최소 구현을 쓴다**

`app/session.py`:

```python
"""세션 상태와 도메인 규칙. Claude 도 HTTP 도 모른다.

시각은 언제나 now 인자로 받는다 — 그래야 120초 잠금을 sleep 없이 테스트한다.
"""
import math
import random
from dataclasses import dataclass, field

from app import config, engine
from app.engine import PriceState
from app.models import NewsItem, NewsPlan


class TradeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GameSession:
    session_id: str
    rng: random.Random
    started_at: float
    prices: PriceState
    cash: int
    holdings: dict[str, int] = field(default_factory=dict)
    round_no: int = 1
    round_start_equity: int = config.SEED_CASH
    target: int = config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER
    analyses_left: int = config.ANALYSES_PER_ROUND
    grind_count: int = 0
    grind_until: float | None = None
    plans: list[NewsPlan] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)


def new_session(session_id: str, rng: random.Random, started_at: float) -> GameSession:
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        prices=engine.new_state(),
        cash=config.SEED_CASH,
        round_start_equity=config.SEED_CASH,
        target=config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER,
    )


def equity(sess: GameSession) -> int:
    """현금 + 보유 평가액. 전부 내림한 정수."""
    valuation = sum(
        engine.price_of(sess.prices, symbol) * qty
        for symbol, qty in sess.holdings.items()
    )
    return sess.cash + valuation


def _fee(gross: int) -> int:
    return math.floor(gross * config.TRADE_FEE_RATE)


def _check_symbol(symbol: str) -> None:
    if symbol not in config.STOCKS:
        raise TradeError("unknown_symbol", f"없는 종목입니다: {symbol}")


def _check_qty(qty: int) -> None:
    if qty <= 0:
        raise TradeError("bad_quantity", "수량은 1주 이상이어야 합니다.")


def max_affordable(sess: GameSession, symbol: str) -> int:
    """수수료까지 감당할 수 있는 최대 수량."""
    _check_symbol(symbol)
    price = engine.price_of(sess.prices, symbol)
    qty = sess.cash // price
    while qty > 0 and price * qty + _fee(price * qty) > sess.cash:
        qty -= 1
    return qty


def buy(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_symbol(symbol)
    _check_qty(qty)
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    if gross + fee > sess.cash:
        raise TradeError("insufficient_cash", "현금이 부족합니다.")
    sess.cash -= gross + fee
    sess.holdings[symbol] = sess.holdings.get(symbol, 0) + qty
    return {"side": "buy", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}


def sell(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_symbol(symbol)
    _check_qty(qty)
    held = sess.holdings.get(symbol, 0)
    if qty > held:
        raise TradeError("insufficient_shares", "보유 수량이 부족합니다.")
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    sess.cash += gross - fee
    if held == qty:
        del sess.holdings[symbol]
    else:
        sess.holdings[symbol] = held - qty
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_trade.py -v`
Expected: PASS — 14 passed

- [ ] **Step 5: 커밋**

```bash
git add app/session.py tests/test_trade.py
git commit -m "feat: 매매와 양방향 수수료

체결·평가액 계산의 반올림을 전부 내림으로 통일한다. 방향이 섞이면
총자산이 몇 원씩 어긋나 파산 판정이 흔들린다."
```

---

### Task 4: 파산, 노가다, 라운드 전환, 분석 차감

**Files:**
- Modify: `app/session.py` (Task 3에서 만든 파일 끝에 추가)
- Test: `tests/test_session_rules.py`

**Interfaces:**
- Consumes: Task 3의 `GameSession`, `TradeError`, `equity`, `buy`, `sell`
- Produces:
  - `session.is_bankrupt(sess: GameSession) -> bool`
  - `session.is_locked(sess: GameSession, now: float) -> bool`
  - `session.lock_remaining(sess: GameSession, now: float) -> int`
  - `session.grind_payout(grind_count: int) -> int`
  - `session.start_grind(sess: GameSession, now: float) -> dict`
  - `session.settle_grind(sess: GameSession, now: float) -> int` — 잠금이 끝났으면 미지급 보수를 넣고 금액 반환, 아니면 0
  - `session.spend_analysis(sess: GameSession, now: float) -> None`
  - `session.goal_reached(sess: GameSession) -> bool`
  - `session.advance_round(sess: GameSession) -> None`
  - Task 3의 `buy`/`sell`에 잠금 검사가 추가된다 (동작 변경)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_session_rules.py`:

```python
import math
import random

import pytest

from app import config
from app.session import (
    TradeError,
    advance_round,
    buy,
    equity,
    goal_reached,
    grind_payout,
    is_bankrupt,
    is_locked,
    lock_remaining,
    new_session,
    settle_grind,
    spend_analysis,
    start_grind,
)


def fresh():
    return new_session("s1", random.Random(0), started_at=0.0)


def broke(cash=50_000):
    sess = fresh()
    sess.cash = cash
    sess.holdings = {}
    return sess


# ---------------------------------------------------------------- 파산 판정

def test_not_bankrupt_at_seed():
    assert is_bankrupt(fresh()) is False


def test_bankrupt_below_threshold():
    assert is_bankrupt(broke(config.BANKRUPTCY_THRESHOLD - 1)) is True


def test_not_bankrupt_exactly_at_threshold():
    assert is_bankrupt(broke(config.BANKRUPTCY_THRESHOLD)) is False


def test_holdings_count_toward_solvency():
    """주식을 들고 있으면 팔 수 있으니 파산이 아니다."""
    sess = fresh()
    buy(sess, "geno", 20, now=0.0)
    sess.cash = 0
    assert is_bankrupt(sess) is False


def test_trading_still_allowed_while_bankrupt():
    """노가다는 막힌 길이 아니라 추가로 생기는 선택지다."""
    sess = broke(50_000)
    buy(sess, "taesan", 1, now=0.0)
    assert sess.holdings["taesan"] == 1


# ---------------------------------------------------------------- 노가다

def test_grind_payout_decays_by_round():
    assert grind_payout(0) == 200_000
    assert grind_payout(1) == 120_000
    assert grind_payout(2) == 72_000
    assert grind_payout(3) == 43_200


def test_grind_payout_keeps_decaying_and_never_goes_negative():
    payouts = [grind_payout(n) for n in range(0, 14)]
    assert payouts[:5] == [200_000, 120_000, 72_000, 43_200, 25_920]
    for earlier, later in zip(payouts, payouts[1:]):
        assert later < earlier
    assert payouts[-1] >= 0


def test_start_grind_locks_for_the_configured_duration():
    sess = broke()
    info = start_grind(sess, now=1000.0)
    assert info["payout"] == 200_000
    assert info["unlock_at"] == 1000.0 + config.GRIND_LOCK_SECONDS
    assert is_locked(sess, now=1000.0) is True
    assert is_locked(sess, now=1000.0 + config.GRIND_LOCK_SECONDS - 1) is True
    assert is_locked(sess, now=1000.0 + config.GRIND_LOCK_SECONDS) is False


def test_grind_pays_nothing_until_the_lock_expires():
    sess = broke(50_000)
    start_grind(sess, now=0.0)
    assert settle_grind(sess, now=60.0) == 0
    assert sess.cash == 50_000
    assert settle_grind(sess, now=config.GRIND_LOCK_SECONDS) == 200_000
    assert sess.cash == 250_000


def test_grind_settles_only_once():
    sess = broke(50_000)
    start_grind(sess, now=0.0)
    settle_grind(sess, now=200.0)
    assert settle_grind(sess, now=300.0) == 0
    assert sess.cash == 250_000


def test_second_grind_pays_less():
    sess = broke(0)
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    sess.cash = 0
    start_grind(sess, now=1000.0)
    settle_grind(sess, now=1000.0 + config.GRIND_LOCK_SECONDS)
    assert sess.cash == 120_000


def test_grind_requires_bankruptcy():
    with pytest.raises(TradeError) as excinfo:
        start_grind(fresh(), now=0.0)
    assert excinfo.value.code == "not_bankrupt"


def test_grind_cannot_be_started_while_already_locked():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        start_grind(sess, now=10.0)
    assert excinfo.value.code == "locked"


def test_lock_remaining_counts_down():
    sess = broke()
    start_grind(sess, now=500.0)
    assert lock_remaining(sess, now=500.0) == config.GRIND_LOCK_SECONDS
    assert lock_remaining(sess, now=560.0) == config.GRIND_LOCK_SECONDS - 60
    assert lock_remaining(sess, now=9999.0) == 0


def test_trading_is_blocked_while_grinding():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "taesan", 1, now=30.0)
    assert excinfo.value.code == "locked"


def test_trading_resumes_after_the_lock():
    sess = broke()
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    buy(sess, "taesan", 1, now=config.GRIND_LOCK_SECONDS)
    assert sess.holdings["taesan"] == 1


# ---------------------------------------------------------------- 분석 차감

def test_analysis_budget_runs_out_after_five():
    sess = fresh()
    for _ in range(config.ANALYSES_PER_ROUND):
        spend_analysis(sess, now=0.0)
    assert sess.analyses_left == 0
    with pytest.raises(TradeError) as excinfo:
        spend_analysis(sess, now=0.0)
    assert excinfo.value.code == "no_analyses_left"


def test_analysis_is_blocked_while_grinding():
    sess = broke()
    start_grind(sess, now=0.0)
    with pytest.raises(TradeError) as excinfo:
        spend_analysis(sess, now=5.0)
    assert excinfo.value.code == "locked"


# ---------------------------------------------------------------- 라운드

def test_goal_not_reached_at_seed():
    assert goal_reached(fresh()) is False


def test_goal_reached_at_target():
    sess = fresh()
    sess.cash = sess.target
    assert goal_reached(sess) is True


def test_advance_round_triples_the_target_and_refills():
    sess = fresh()
    sess.cash = 3_000_000
    sess.analyses_left = 0
    sess.grind_count = 2

    advance_round(sess)

    assert sess.round_no == 2
    assert sess.round_start_equity == 3_000_000
    assert sess.target == 9_000_000
    assert sess.analyses_left == config.ANALYSES_PER_ROUND
    assert sess.grind_count == 0


def test_grind_payout_resets_with_the_round():
    """라운드가 넘어가면 노가다 회차가 초기화되어 다시 20만부터다."""
    sess = fresh()
    sess.grind_count = 3
    sess.cash = sess.target
    advance_round(sess)
    sess.cash = 0
    start_grind(sess, now=0.0)
    settle_grind(sess, now=config.GRIND_LOCK_SECONDS)
    assert sess.cash == 200_000
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_session_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'advance_round' from 'app.session'`

- [ ] **Step 3: `buy`/`sell`에 잠금 검사를 넣는다**

`app/session.py`의 `buy`와 `sell`을 아래로 통째로 교체한다. 달라진 것은 첫 줄의 `_check_unlocked(sess, now)` 하나뿐이고, `_check_symbol` **앞**에 둔다 — 잠긴 동안에는 어떤 주문도 검증조차 하지 않는다.

```python
def buy(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_unlocked(sess, now)
    _check_symbol(symbol)
    _check_qty(qty)
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    if gross + fee > sess.cash:
        raise TradeError("insufficient_cash", "현금이 부족합니다.")
    sess.cash -= gross + fee
    sess.holdings[symbol] = sess.holdings.get(symbol, 0) + qty
    return {"side": "buy", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}


def sell(sess: GameSession, symbol: str, qty: int, now: float) -> dict:
    _check_unlocked(sess, now)
    _check_symbol(symbol)
    _check_qty(qty)
    held = sess.holdings.get(symbol, 0)
    if qty > held:
        raise TradeError("insufficient_shares", "보유 수량이 부족합니다.")
    price = engine.price_of(sess.prices, symbol)
    gross = price * qty
    fee = _fee(gross)
    sess.cash += gross - fee
    if held == qty:
        del sess.holdings[symbol]
    else:
        sess.holdings[symbol] = held - qty
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "gross": gross, "fee": fee}
```

- [ ] **Step 4: `GameSession`에 `pending_payout` 필드를 추가한다**

`app/session.py`의 `GameSession` dataclass에서 `grind_until` 다음 줄에 넣는다. 다음 스텝의 함수들이 이 필드를 쓰므로 먼저 만든다.

```python
    grind_until: float | None = None
    pending_payout: int = 0
```

- [ ] **Step 5: 규칙 함수를 `app/session.py` 끝에 추가한다**

```python
# ------------------------------------------------------- 파산과 노가다

def is_bankrupt(sess: GameSession) -> bool:
    return equity(sess) < config.BANKRUPTCY_THRESHOLD


def is_locked(sess: GameSession, now: float) -> bool:
    return sess.grind_until is not None and now < sess.grind_until


def lock_remaining(sess: GameSession, now: float) -> int:
    if sess.grind_until is None:
        return 0
    return max(0, math.ceil(sess.grind_until - now))


def _check_unlocked(sess: GameSession, now: float) -> None:
    if is_locked(sess, now):
        raise TradeError("locked", "노가다 중에는 조작할 수 없습니다.")


def grind_payout(grind_count: int) -> int:
    """회차마다 3/5 배로 줄어든다. 1회차가 grind_count == 0 이다.

    부동소수점으로 계산하면 4회차가 43,199 로 어긋나므로 정수 나눗셈을 쓴다.
    """
    return (
        config.GRIND_BASE_PAYOUT
        * config.GRIND_DECAY_NUM ** grind_count
        // config.GRIND_DECAY_DEN ** grind_count
    )


def start_grind(sess: GameSession, now: float) -> dict:
    # 이전 노가다의 미지급 보수를 먼저 정산한다. 잠금이 자연히 풀린 뒤 정산 없이
    # 다시 시작하면 pending_payout 이 덮어써져 미지급액이 영구히 사라진다.
    settle_grind(sess, now)
    _check_unlocked(sess, now)
    if not is_bankrupt(sess):
        raise TradeError("not_bankrupt", "파산 상태에서만 노가다를 할 수 있습니다.")
    payout = grind_payout(sess.grind_count)
    sess.grind_until = now + config.GRIND_LOCK_SECONDS
    sess.pending_payout = payout
    sess.grind_count += 1
    return {"payout": payout, "unlock_at": sess.grind_until}


def settle_grind(sess: GameSession, now: float) -> int:
    """잠금이 끝났으면 미지급 보수를 현금에 넣고 그 금액을 돌려준다."""
    if sess.pending_payout == 0 or is_locked(sess, now):
        return 0
    payout = sess.pending_payout
    sess.cash += payout
    sess.pending_payout = 0
    sess.grind_until = None
    return payout


# ------------------------------------------------------------ 분석 차감

def spend_analysis(sess: GameSession, now: float) -> None:
    _check_unlocked(sess, now)
    if sess.analyses_left <= 0:
        raise TradeError("no_analyses_left", "이 라운드의 분석 횟수를 다 썼습니다.")
    sess.analyses_left -= 1


# --------------------------------------------------------------- 라운드

def goal_reached(sess: GameSession) -> bool:
    return equity(sess) >= sess.target


def advance_round(sess: GameSession) -> None:
    current = equity(sess)
    sess.round_no += 1
    sess.round_start_equity = current
    sess.target = current * config.ROUND_TARGET_MULTIPLIER
    sess.analyses_left = config.ANALYSES_PER_ROUND
    sess.grind_count = 0
```

`start_grind` 가 `settle_grind` 를 호출하므로, 위 코드 블록의 정의 순서를 그대로 유지한다
(`settle_grind` 가 파일에서 먼저 정의된다). 순서를 바꾸면 모듈 로드 시점에는 문제가 없지만
읽는 사람이 호출 방향을 거꾸로 이해한다.

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_session_rules.py tests/test_trade.py -v`
Expected: PASS — 38 passed (신규 규칙 24건 + Task 3 매매 14건)

- [ ] **Step 7: 커밋**

```bash
git add app/session.py tests/test_session_rules.py
git commit -m "feat: 파산 판정, 노가다 감쇠, 라운드 전환

노가다 보수는 회차마다 0.6배로 줄어든다. 잠금 시간은 120초 고정이라
벌칙이 시간이 아니라 점점 무의미해지는 금액으로 온다.
파산 상태에서도 매매는 열려 있다 — 노가다는 추가 선택지다."
```

---

### Task 5: 로컬 폴백 — 템플릿 뉴스와 등급 해설

Claude 없이 게임이 온전히 돌아가게 만든다. 이것이 있어야 테스트가 API를 부르지 않고, 키가 없거나 네트워크가 끊겨도 게임이 멈추지 않는다.

**Files:**
- Create: `app/fallback.py`
- Test: `tests/test_fallback.py`

**Interfaces:**
- Consumes: `config`, `models.NewsPlan`/`NewsItem` (Task 1)
- Produces:
  - `fallback.strength_of(impact: float) -> str` — `"up_strong"`, `"up_weak"`, `"none"`, `"down_weak"`, `"down_strong"`
  - `fallback.STRENGTH_LABELS: dict[str, str]` — 등급 → 한국어 라벨
  - `fallback.write_news(plans: Sequence[NewsPlan], rng: random.Random) -> list[NewsItem]`
  - `fallback.write_commentary(item: NewsItem) -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_fallback.py`:

```python
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

    위 테스트는 "정답에 의존하지 않음" 을, 이 테스트는 "톤에는 제대로 의존함" 을
    보장한다. 두 풀을 똑같이 만들어버리는 회귀는 이쪽만 잡는다.
    """
    from app.fallback import (
        _NEGATIVE_BODIES,
        _NEGATIVE_HEADLINES,
        _POSITIVE_BODIES,
        _POSITIVE_HEADLINES,
    )

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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_fallback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fallback'`

- [ ] **Step 3: 최소 구현을 쓴다**

`app/fallback.py`:

```python
"""Claude 없이 뉴스와 해설을 만든다.

키가 없든 네트워크가 끊기든 레이트리밋이든 정책 거절이든, 전부 이 경로로
떨어진다. 테스트도 여기만 쓴다 — Claude 를 한 번도 부르지 않는다.
"""
import random
from collections.abc import Sequence

from app import config
from app.models import NewsItem, NewsPlan

STRENGTH_LABELS: dict[str, str] = {
    "up_strong": "강한 상승",
    "up_weak": "약한 상승",
    "none": "무영향",
    "down_weak": "약한 하락",
    "down_strong": "강한 하락",
}

_POSITIVE_HEADLINES = (
    "{name}, 분기 실적 시장 기대치 상회",
    "{name}, 대형 공급계약 체결 소식",
    "{name} 신규 설비 조기 가동… 출하 확대 전망",
    "{name}, 해외 인증 절차 최종 통과",
    "{name} 주요 제품 단가 인상 반영",
)
_NEGATIVE_HEADLINES = (
    "{name}, 분기 실적 시장 기대치 하회",
    "{name} 주요 고객사 발주 축소 통보",
    "{name} 생산 라인 일시 중단… 출하 지연 우려",
    "{name}, 규제 당국 현장 점검 착수",
    "{name} 원가 부담 확대로 수익성 압박",
)

_POSITIVE_BODIES = (
    "회사는 {sector} 부문 수요 회복을 근거로 제시했다. 구체적인 수치는 공개하지 않았다.",
    "업계는 {sector} 업황 개선의 신호로 보고 있으나 지속성에는 유보적인 평가가 나온다.",
    "{sector} 업종 전반의 흐름과 맞물린 결과라는 해석이 나온다.",
)
_NEGATIVE_BODIES = (
    "회사는 {sector} 부문 수요 둔화를 원인으로 들었다. 구체적인 규모는 밝히지 않았다.",
    "업계는 {sector} 업황 조정 국면의 일부로 보고 있으나 폭을 두고는 의견이 갈린다.",
    "{sector} 업종 전반의 부담이 함께 작용했다는 평가가 나온다.",
)

_COMMENTARY = {
    "up_strong": "본문의 내용은 실적에 직접 반영될 재료다. 판정: {label}. 램프가 끝나기 전이라면 아직 먹을 몫이 남아 있다.",
    "up_weak": "재료는 맞지만 규모가 작다. 판정: {label}. 수수료를 감안하면 남는 몫이 크지 않다.",
    "none": "이미 알려진 내용의 재인용이거나 규모가 미미하다. 판정: {label}. 들어갈 이유가 없다.",
    "down_weak": "표면과 달리 실제 부담이 있다. 판정: {label}. 크지 않지만 방향은 아래다.",
    "down_strong": "표면의 톤과 실제 영향이 어긋난다. 판정: {label}. 지금 들어가면 정면으로 물린다.",
}


def strength_of(impact: float) -> str:
    """임팩트 절대값으로 5단계 등급을 매긴다. 원시 수치는 밖으로 내보내지 않는다."""
    magnitude = abs(impact)
    if magnitude < config.STRENGTH_WEAK_MIN:
        return "none"
    if magnitude >= config.STRENGTH_STRONG_MIN:
        return "up_strong" if impact > 0 else "down_strong"
    return "up_weak" if impact > 0 else "down_weak"


def write_news(plans: Sequence[NewsPlan], rng: random.Random) -> list[NewsItem]:
    """계획마다 문장을 채운다. 문장은 surface_tone 만 따르고 impact 는 보지 않는다."""
    items: list[NewsItem] = []
    for plan in plans:
        stock = config.STOCKS[plan.symbol]
        positive = plan.surface_tone == "positive"
        headlines = _POSITIVE_HEADLINES if positive else _NEGATIVE_HEADLINES
        bodies = _POSITIVE_BODIES if positive else _NEGATIVE_BODIES
        items.append(
            NewsItem(
                plan=plan,
                headline=rng.choice(headlines).format(name=stock.name),
                body=rng.choice(bodies).format(sector=stock.sector),
                offline=True,
            )
        )
    return items


def write_commentary(item: NewsItem) -> str:
    """확정된 등급을 사람 말로 옮긴다. 판정은 여기서 다시 하지 않는다."""
    strength = strength_of(item.plan.impact)
    return _COMMENTARY[strength].format(label=STRENGTH_LABELS[strength])
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_fallback.py -v`
Expected: PASS — 21 passed

- [ ] **Step 5: 커밋**

```bash
git add app/fallback.py tests/test_fallback.py
git commit -m "feat: 로컬 폴백 뉴스 생성과 등급 해설

문장은 surface_tone 만 보고 impact 는 보지 않는다 — 문장에서 낚시가
들통나면 메커니즘이 무너진다. 테스트는 전부 이 경로만 쓴다."
```

---

### Task 6: Claude 어댑터

Claude를 아는 유일한 두 파일. 실패는 전부 Task 5의 폴백으로 흡수하므로 나머지 코드에 분기가 새지 않는다.

> **구현 중 확정된 변경 (커밋 `ab6982b` 이 최종)**: 아래 코드 블록은 두 곳이 낡았다.
> (1) 실패 경로가 다섯 개가 아니라 **여섯 개**다 — Claude 가 건수는 맞지만 빈 헤드라인이나
> 빈 본문을 돌려주는 경우가 빠져 있었고, 그것이 `offline=False` 로 플레이어에게 도달했다.
> (2) 거절·건수 불일치는 예외가 아닌 조건이므로 `raise RuntimeError` 로 자기 `except` 에
> 던지지 않는다. `try` 는 SDK 호출만 감싸고, 쓸 수 없는 응답은 사유 문자열을 돌려주는
> `_unusable(response, plans)` 헬퍼와 평범한 `if` 로 처리한다. 그래야 로그의 트레이스백이
> 진짜 장애만 뜻한다. 또 두 시스템 프롬프트의 실존 엔티티 금지 조항에 `기관` 과
> "실존 여부가 불분명하면 지어내지 말고 일반명사로 씁니다" 를 넣었다.

**Files:**
- Create: `app/news.py`
- Create: `app/analysis.py`
- Test: `tests/test_claude_adapters.py`

**Interfaces:**
- Consumes: `config`, `models` (Task 1), `fallback` (Task 5)
- Produces:
  - `news.NewsText` — Pydantic 모델, 필드 `headline: str`, `body: str`
  - `news.NewsBatch` — Pydantic 모델, 필드 `items: list[NewsText]`
  - `news.build_news_prompt(plans: Sequence[NewsPlan]) -> str` — 낚시 은닉의 경계라 공개 함수로 두고 직접 테스트한다
  - `news.fetch_news(plans: Sequence[NewsPlan], rng: random.Random, client) -> list[NewsItem]` — `client=None`이면 곧바로 폴백
  - `analysis.Commentary` — Pydantic 모델, 필드 `commentary: str`
  - `analysis.build_analysis_prompt(item: NewsItem) -> str`
  - `analysis.fetch_commentary(item: NewsItem, client) -> tuple[str, bool]` — `(해설, offline 여부)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_claude_adapters.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_claude_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analysis'`

- [ ] **Step 3: 뉴스 어댑터를 쓴다**

`app/news.py`:

```python
"""뉴스 문장을 확보한다. Claude 를 아는 두 파일 중 하나.

시나리오 표는 이미 확정돼 있고 Claude 는 문장만 채운다. kind 와 impact 는
프롬프트에 넣지 않는다 — 실제 임팩트를 알면 역방향 기사에 우려 표현을
흘려서 문장만 읽고 낚시를 알아채게 된다.
"""
import logging
import random
from collections.abc import Sequence

from pydantic import BaseModel

from app import config, fallback
from app.models import NewsItem, NewsPlan

log = logging.getLogger(__name__)

SYSTEM = """당신은 한국 증권 뉴스 와이어의 기자입니다.
주어진 목록의 각 항목에 대해 헤드라인 한 줄과 본문 2~3문장을 씁니다.

규칙:
- 항목 순서를 그대로 유지하고, 항목 수와 같은 개수를 반환합니다.
- tone 이 positive 면 호재로 읽히는 기사, negative 면 악재로 읽히는 기사를 씁니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·정책 사업의 이름을 쓰지 않습니다.
- 실제 통신사 기사처럼 건조하게 씁니다. 투자 권유 표현은 쓰지 않습니다.
- 기사의 톤은 주어진 tone 만 따릅니다. 그 밖의 판단을 문장에 담지 않습니다."""


class NewsText(BaseModel):
    headline: str
    body: str


class NewsBatch(BaseModel):
    items: list[NewsText]


def build_news_prompt(plans: Sequence[NewsPlan]) -> str:
    """회사·업종·톤만 넣는다. kind 와 impact 는 절대 넣지 않는다."""
    lines = [f"기사 {len(plans)}건을 써 주세요.", ""]
    for index, plan in enumerate(plans, start=1):
        stock = config.STOCKS[plan.symbol]
        lines.append(
            f"{index}. 회사={stock.name} / 업종={stock.sector} / tone={plan.surface_tone}"
        )
    return "\n".join(lines)


def fetch_news(
    plans: Sequence[NewsPlan],
    rng: random.Random,
    client,
) -> list[NewsItem]:
    """Claude 로 문장을 채우고, 어떤 실패든 로컬 템플릿으로 떨어진다."""
    if client is None or not plans:
        return fallback.write_news(plans, rng)

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_news_prompt(plans)}],
            thinking={"type": "adaptive"},
            output_config={"effort": config.NEWS_EFFORT},
            output_format=NewsBatch,
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError("모델이 요청을 거절했습니다.")
        batch = response.parsed_output
        if batch is None or len(batch.items) != len(plans):
            raise RuntimeError("기사 개수가 요청과 다릅니다.")
    except Exception:
        log.warning("뉴스 생성 실패 — 로컬 템플릿으로 대체합니다.", exc_info=True)
        return fallback.write_news(plans, rng)

    return [
        NewsItem(plan=plan, headline=text.headline, body=text.body, offline=False)
        for plan, text in zip(plans, batch.items)
    ]
```

- [ ] **Step 4: 분석 어댑터를 쓴다**

`app/analysis.py`:

```python
"""분석 해설을 확보한다. Claude 를 아는 두 파일 중 하나.

뉴스 생성과 반대로 여기서는 정답을 전부 알려준다. Claude 에게 판정을
맡기면 확실한 정답이 매번 흔들리고 가격 엔진과 어긋난다. 등급은 서버가
확정하고 Claude 는 그 판정의 근거를 기사 안에서 찾아 설명만 한다.
"""
import logging

from pydantic import BaseModel

from app import config, fallback
from app.models import NewsItem

log = logging.getLogger(__name__)

SYSTEM = """당신은 증권사 애널리스트입니다.
기사와 확정된 판정을 받고, 그 판정이 왜 그런지를 기사 안의 표현을 근거로 설명합니다.

규칙:
- 판정은 이미 정해져 있습니다. 다시 판단하거나 뒤집지 않습니다.
- 기사에 실제로 있는 표현을 근거로 삼습니다.
- 2~3문장, 건조한 애널리스트 어투로 씁니다.
- 수치나 확률을 새로 만들어내지 않습니다. 투자 권유 표현은 쓰지 않습니다."""


class Commentary(BaseModel):
    commentary: str


def build_analysis_prompt(item: NewsItem) -> str:
    """기사 전문과 확정된 등급 라벨을 넣는다. 원시 임팩트 수치는 넣지 않는다."""
    stock = config.STOCKS[item.plan.symbol]
    label = fallback.STRENGTH_LABELS[fallback.strength_of(item.plan.impact)]
    return (
        f"회사: {stock.name} ({stock.sector})\n"
        f"헤드라인: {item.headline}\n"
        f"본문: {item.body}\n\n"
        f"확정된 판정: {label}\n\n"
        "이 판정의 근거를 기사 안의 표현에서 찾아 설명해 주세요."
    )


def fetch_commentary(item: NewsItem, client) -> tuple[str, bool]:
    """(해설, offline 여부). 어떤 실패든 로컬 문장으로 떨어진다."""
    if client is None:
        return fallback.write_commentary(item), True

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_analysis_prompt(item)}],
            thinking={"type": "adaptive"},
            output_config={"effort": config.ANALYSIS_EFFORT},
            output_format=Commentary,
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError("모델이 요청을 거절했습니다.")
        parsed = response.parsed_output
        if parsed is None or not parsed.commentary.strip():
            raise RuntimeError("빈 해설이 돌아왔습니다.")
    except Exception:
        log.warning("분석 해설 실패 — 로컬 문장으로 대체합니다.", exc_info=True)
        return fallback.write_commentary(item), True

    return parsed.commentary, False
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_claude_adapters.py -v`
Expected: PASS — 13 passed

- [ ] **Step 6: 전체 테스트를 돌린다**

Run: `.venv/bin/pytest -v`
Expected: PASS — 84 passed. `ANTHROPIC_API_KEY` 없이 통과해야 한다. 확인:

```bash
env -u ANTHROPIC_API_KEY .venv/bin/pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add app/news.py app/analysis.py tests/test_claude_adapters.py
git commit -m "feat: Claude 어댑터 — 뉴스 생성과 분석 해설

뉴스 프롬프트에는 kind/impact 를 넣지 않고, 분석 프롬프트에는 전부 넣는다.
Claude 는 판정자가 아니라 해설자다. 모든 실패는 폴백으로 흡수한다."
```

---

### Task 7: HTTP API

**Files:**
- Create: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: 전 태스크 전부
- Produces: 실행 가능한 ASGI 앱 `app.main:app`, 엔드포인트 6개

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_api.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: 최소 구현을 쓴다**

`app/main.py`:

```python
"""FastAPI 라우트. 계산 로직은 담지 않는다.

GET /api/state 요청이 tick 을 증분 진행한다. 같은 세션의 동시 요청이
tick 을 두 번 밀지 않도록 세션마다 asyncio.Lock 을 하나 둔다.
"""
import asyncio
import os
import random
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import analysis, config, engine, fallback, news, session as rules
from app.models import NewsPlan
from app.scenario import build_plans
from app.session import GameSession, TradeError

app = FastAPI(title="모의주식게임")

sessions: dict[str, GameSession] = {}
_locks: dict[str, asyncio.Lock] = {}


def _client():
    """키가 없으면 None — 그 경우 어댑터가 폴백으로 떨어진다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    return anthropic.Anthropic()


def _get(session_id: str) -> GameSession:
    sess = sessions.get(session_id)
    if sess is None:
        raise HTTPException(404, {"code": "no_session", "message": "게임이 만료됐습니다."})
    return sess


def _lock(session_id: str) -> asyncio.Lock:
    return _locks.setdefault(session_id, asyncio.Lock())


def _fail(error: TradeError) -> HTTPException:
    status = 423 if error.code == "locked" else 400
    return HTTPException(status, {"code": error.code, "message": error.message})


def _tick_of(sess: GameSession, now: float) -> int:
    return int((now - sess.started_at) / config.TICK_SECONDS)


def _sync(sess: GameSession, now: float) -> int:
    """tick 을 현재까지 진행하고 노가다 보수를 정산한다."""
    tick = _tick_of(sess, now)
    engine.advance(sess.prices, sess.plans, tick, sess.rng)
    rules.settle_grind(sess, now)
    return tick


def _stock_rows(sess: GameSession) -> list[dict]:
    rows = []
    for symbol, stock in config.STOCKS.items():
        price = engine.price_of(sess.prices, symbol)
        rows.append({
            "symbol": symbol,
            "name": stock.name,
            "sector": stock.sector,
            "price": price,
            "change_pct": round((price / stock.base_price - 1) * 100, 2),
            "held": sess.holdings.get(symbol, 0),
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


def _snapshot(sess: GameSession, now: float, since: int = -1) -> dict:
    tick = _sync(sess, now)
    return {
        "session_id": sess.session_id,
        "tick": tick,
        "round_no": sess.round_no,
        "cash": sess.cash,
        "equity": rules.equity(sess),
        "target": sess.target,
        "round_start_equity": sess.round_start_equity,
        "analyses_left": sess.analyses_left,
        "bankrupt": rules.is_bankrupt(sess),
        "locked": rules.is_locked(sess, now),
        "lock_remaining": rules.lock_remaining(sess, now),
        "grind_count": sess.grind_count,
        "goal_reached": rules.goal_reached(sess),
        "stocks": _stock_rows(sess),
        "news": _news_rows(sess, tick, since),
        "news_total": len(sess.news),
    }


_refilling: set[str] = set()


def _pending_count(sess: GameSession, tick: int) -> int:
    """아직 등장하지 않은 뉴스 건수."""
    return sum(1 for plan in sess.plans if plan.publish_tick > tick)


def _next_batch_plans(sess: GameSession, count: int) -> list[NewsPlan]:
    last_tick = sess.plans[-1].publish_tick if sess.plans else 0
    return build_plans(
        count,
        sess.round_no,
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
        items = await asyncio.to_thread(news.fetch_news, plans, sess.rng, _client())
        sess.plans.extend(plans)
        sess.news.extend(items)
    finally:
        _refilling.discard(sess.session_id)


class SessionBody(BaseModel):
    session_id: str


class TradeBody(SessionBody):
    symbol: str
    side: str
    qty: int = Field(gt=0)


class AnalyzeBody(SessionBody):
    news_id: int


@app.post("/api/game")
async def new_game(background: BackgroundTasks) -> dict:
    now = time.monotonic()
    session_id = uuid.uuid4().hex
    rng = random.Random()
    sess = rules.new_session(session_id, rng, started_at=now)

    # 첫 배치만 기다린다. 20건을 한 번에 기다리면 게임 시작이 10초를 넘는다.
    first = build_plans(
        config.NEWS_FIRST_WAIT_COUNT, sess.round_no, rng,
        first_news_id=0, first_tick=0,
    )
    sess.plans.extend(first)
    sess.news.extend(
        await asyncio.to_thread(news.fetch_news, first, rng, _client())
    )
    sessions[session_id] = sess
    background.add_task(
        _refill, sess, config.NEWS_BATCH_SIZE - config.NEWS_FIRST_WAIT_COUNT
    )
    return _snapshot(sess, now)


@app.get("/api/state")
async def get_state(
    session_id: str, background: BackgroundTasks, since: int = -1
) -> dict:
    sess = _get(session_id)
    async with _lock(session_id):
        snapshot = _snapshot(sess, time.monotonic(), since)
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
        result["cash"] = sess.cash
        result["equity"] = rules.equity(sess)
        return result


@app.post("/api/analyze")
async def analyze(body: AnalyzeBody) -> dict:
    sess = _get(body.session_id)
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


@app.post("/api/next-round")
async def next_round(body: SessionBody) -> dict:
    sess = _get(body.session_id)
    async with _lock(body.session_id):
        now = time.monotonic()
        _sync(sess, now)
        if not rules.goal_reached(sess):
            raise HTTPException(
                400, {"code": "goal_not_reached", "message": "목표 자산에 아직 닿지 않았습니다."}
            )
        rules.advance_round(sess)
        return _snapshot(sess, now)


if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS — 20 passed

- [ ] **Step 5: 전체 테스트를 키 없이 돌린다**

Run: `env -u ANTHROPIC_API_KEY .venv/bin/pytest -q`
Expected: PASS — 106 passed

- [ ] **Step 6: 실제로 한 판을 손으로 돌려본다**

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

다른 터미널에서:

```bash
SID=$(curl -s -X POST localhost:8000/api/game | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -s "localhost:8000/api/state?session_id=$SID" | python3 -m json.tool | head -40
curl -s -X POST localhost:8000/api/trade -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"symbol\":\"geno\",\"side\":\"buy\",\"qty\":3}" | python3 -m json.tool
```

확인할 것: 가격이 요청마다 조금씩 달라진다(tick 이 진행된다). 뉴스가 시간이 지나면 늘어난다. `state` 응답 어디에도 `impact`/`kind` 가 없다.

- [ ] **Step 7: 커밋**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: HTTP API — 게임 시작, 상태 폴링, 매매, 분석, 노가다, 라운드

GET /api/state 가 tick 을 증분 진행한다. 세션마다 asyncio.Lock 을 두어
동시 요청이 tick 을 두 번 밀지 않게 한다. 응답에 impact/kind 를 싣지 않는다."
```

---

## 완료 후 상태

- `pytest` 106건이 `ANTHROPIC_API_KEY` 없이 통과한다.
- `uvicorn app.main:app` 으로 서버가 뜨고, `curl` 만으로 한 판을 목표 달성까지 플레이할 수 있다.
- `ANTHROPIC_API_KEY` 를 넣으면 뉴스와 해설이 Claude 문장으로 바뀐다. 빼면 템플릿으로 돌아간다 — 어느 쪽이든 게임은 멈추지 않는다.

## 스펙과 다르게 결정한 부분

계획을 쓰면서 스펙과 달라진 곳이 넷 있다. 구현 중 헷갈리지 않도록 여기 적어둔다.

**1. 뉴스 배치를 스트리밍하지 않는다.** 스펙은 출력이 약 7K 토큰이라 스트리밍을 쓰라고 했다. 그런데 구조화 출력 헬퍼 `client.messages.parse()`와 `.stream()`을 함께 쓰는 조합은 문서화돼 있지 않다. `max_tokens=16000`은 비스트리밍 권장 상한 안에 들어가므로 `parse()`를 그대로 쓰고 스트리밍은 쓰지 않는다. 실제로 타임아웃이 나면 그때 수동 스키마 검증(`output_config.format`) + `.stream()`으로 바꾼다.

**2. 폴백을 `fallback.py`로 분리했다.** 스펙의 파일 구조는 폴백을 `news.py`/`analysis.py` 안에 두었다. 그런데 폴백은 두 파일이 함께 쓰고 테스트도 전부 폴백만 쓰므로, 별도 파일로 두는 쪽이 경계가 깨끗하다. Claude 를 아는 파일은 여전히 `news.py`와 `analysis.py` 둘뿐이다.

**3. `GRIND_DECAY = 0.6` 을 `GRIND_DECAY_NUM = 3` / `GRIND_DECAY_DEN = 5` 로 바꿨다.** 부동소수점으로 계산하면 `200_000 * 0.6 ** 3 = 43199.99...` 가 되어 노가다 4회차 보수가 스펙이 의도한 43,200 이 아니라 43,199 로 어긋난다. 3/5 는 0.6 과 정확히 같으므로 값은 그대로이고 계산만 정수로 바뀐다.

**4. 뉴스 어댑터의 실패 경로가 다섯이 아니라 여섯이다.** 스펙과 계획은 클라이언트 없음·
예외·refusal·`None`·건수 불일치 다섯 가지만 셌다. Claude 가 건수는 맞게 돌려주면서 헤드라인이나
본문을 빈 문자열로 주는 경우가 빠져 있었고, `NewsText.headline` 이 제약 없는 `str` 이라
pydantic 검증을 통과해 `offline=False` 로 플레이어에게 도달했다. 낚시는 플레이어가 실제 기사를
읽는 데 달려 있어 빈 기사는 그 항목을 조용히 무효화한다. 여섯 번째 검사를 추가했다.
Task 6 리뷰에서 발견했다.

**5. 폴백의 격리 가드를 결정론적 2종으로 보강했다.** 브리프의
`test_headline_tone_follows_surface_tone_not_the_real_impact` 는 헤드라인만 검사하고
본문은 무방비였다. 본문 선택을 `plan.impact > 0` 에 의존시켜도 전체 스위트가 통과하는
것을 실제로 확인했다(기존 19건 전부 통과, 새 2건만 실패). 이 게임의 가장 중요한 불변식이
생성 텍스트의 절반만 보호되고 있었다. Task 5 리뷰에서 발견했다.

**6. `start_grind` 가 먼저 정산한다.** 스펙은 노가다의 상태 전이를 이 수준까지 규정하지
않았다. `is_locked` 가 120초 경과 후 정산 여부와 무관하게 `False` 가 되므로, 정산 없이
재시작하면 `pending_payout` 이 덮어써져 미지급 보수가 영구히 사라진다(1회차 200,000원
소실을 재현). `start_grind` 가 맨 먼저 `settle_grind` 를 호출하게 한다. 도메인 계층이
호출자의 호출 순서에 의존해 정확해지면 안 된다. 의도된 귀결: 이전 보수가 파산선을 넘기면
새 노가다는 `not_bankrupt` 로 거부된다. Task 4 리뷰에서 발견했다.

**7. 가격 상태가 로그가격이 아니라 누적 로그수익을 저장한다.** 스펙 3절의 공식은
`log_price(sym, T) = log(base(sym)) + ...` 로 적혀 있는데, 이대로 구현하면
`floor(exp(log(base)))` 가 6종목 중 4종목에서 1원을 잃는다(geno 45000→44999,
pixel 33000→32999, taesan 18500→18499, arawings 24000→23999). tick 0 부터 가격이
어긋나고 그 오차가 모든 평가액·파산 판정에 실린다. 수학적으로 동등한 형태인
`floor(base * exp(누적수익))` 으로 바꾼다 — `exp(0.0)` 이 정확히 `1.0` 이므로 tick 0 가
정확해진다. Task 2 구현 중 발견했다.

**8. `POLL_INTERVAL_MS` 와 `SPARKLINE_TICKS` 를 `config.py` 에 넣지 않았다.** 둘 다 프론트엔드 전용 수치다. 프론트 계획에서 추가한다.

## 이 계획에 없는 것

**프론트엔드.** 미학 방향(A/B/C)이 아직 미선택이라 별도 계획으로 분리했다. 이 계획이 끝나면 `static/` 아래 단일 페이지를 붙이는 계획을 새로 쓴다. API 는 이미 프론트가 필요한 것을 전부 내보내므로(`stocks`, `news`, `locked`, `lock_remaining`, `analyses_left`, `goal_reached`) 프론트 계획은 화면만 다룬다.

스펙의 다음 항목들도 프론트 계획으로 넘어간다: 스파크라인·가격 차트 SVG, 뉴스 램프 구간 표시, 노가다 오버레이, 폴링 백오프와 "연결 끊김" 배지, 상승 빨강/하락 파랑 색 규칙.
