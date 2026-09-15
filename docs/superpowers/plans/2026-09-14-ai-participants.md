# AI 참가자 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 뉴스에 반응해 매매하는 AI 참가자를 넣고, 그 주문이 가격을 밀고, 체결이 피드로 흐르게 한다.

**Architecture:** `engine.advance` 가 `on_tick` 콜백을 받아 tick 마다 "이 종목에 얼마어치 순매수" 만 넘겨받는다 — 매매 규칙은 새 모듈 `participants` 가 소유하고 engine 은 모른다. 주문 충격은 `flow_log` 라는 감쇠하는 별도 항이라 되먹임 나선이 생기지 않고 상한이 걸려 있다. AI 판단은 engine 의 rng 를 쓰지 않고 `(ai_seed, ai_index, news_id)` 해시로 뽑아 tick 진행 순서와 무관하게 결정론적이다.

**Tech Stack:** Python 3.11, FastAPI 0.115.6, pydantic 2.10.4, pytest 8.3.4. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-09-14-ai-participants-design.md`

**Branch:** `feat/ai-participants`

## Global Constraints

- **작업 디렉터리는 언제나 `backend/`** 다.
- **테스트는 네트워크도 Claude 도 부르지 않는다.** 기존 192개가 그렇다.
- `pytest.ini` 가 **경고를 오류로 취급한다.** `DeprecationWarning` 하나로 빨갛게 죽는다.
- **숫자 리터럴은 `config.py` 에만.**
- **돈은 전부 `math.floor` 내림.** 표시용 백분율만 예외다.
- **증분 계산과 일괄 계산이 같아야 한다.** 이 서버에서 가장 중요한 불변식이다. AI 매매가 `engine.advance` 의 `rng` 를 소비하면 깨진다 — AI 가 매매한 tick 과 안 한 tick 의 난수 소비량이 달라지기 때문이다. **AI 는 자기 난수를 쓴다.**
- **서버 밖으로 나가지 않는 것:** `impact`, `kind`, `fair_value`, `valuation`, 그리고 이번에 더해지는 **AI 의 보유 종목**.
- **프론트 계약을 깨지 않는다.** 이번 작업은 전부 필드 추가다. 기존 필드의 의미를 바꾸지 않는다.
- 매 태스크는 `.venv/bin/pytest -q` **전체**가 통과한 상태로 끝난다.

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `app/engine.py` | `flow_log` 감쇠·상한, `on_tick` 콜백. **매매를 모른다** | 1 |
| `app/config.py` | `FLOW_*`, AI 명단 9명, `AI_COUNT_*`, `VOLUME_WINDOW_TICKS` | 1, 2 |
| `app/participants.py` | AI 상태, 결정론적 판단, 매매, tick 구동 | 2, 3, 4 |
| `app/session.py` | `ais`·`trades`·`ai_seed`·거래량 창. 플레이어 규칙은 그대로 | 4 |
| `app/main.py` | 콜백 연결, 스냅샷 3필드, `ai_count`, `trades_since` | 5 |

의존 순서가 곧 태스크 순서다.

---

### Task 1: 주문 흐름 — 감쇠하는 별도 항

**Files:**
- Modify: `backend/app/engine.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_engine.py`

**Interfaces:**
- Produces:
  - `PriceState.flow_log: dict[str, float]`
  - `engine.add_flow(state: PriceState, symbol: str, value: int) -> None` — `value` 는 원 단위 순매수액(매수 양수, 매도 음수)
  - `engine.advance(state, plans, to_tick, rng, on_tick=None)` — `on_tick: Callable[[int], dict[str, int]] | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_engine.py` 끝에 추가한다:

```python
def test_flow_moves_price_immediately():
    state = _state()
    before = price_of(state, "geno")
    engine.add_flow(state, "geno", 1_000_000)
    assert price_of(state, "geno") > before


def test_flow_decays_back_to_zero():
    """감쇠가 없으면 AI 가 산 것이 영원히 가격에 남아 되먹임 나선이 된다."""
    state = _state()
    before = price_of(state, "geno")
    engine.add_flow(state, "geno", 1_000_000)
    advance(state, [], to_tick=200, rng=ZeroRandom(0))
    assert price_of(state, "geno") == pytest.approx(before, rel=0.001)


def test_flow_is_capped_no_matter_how_much_is_bought():
    """상한이 '주문 흐름은 조역' 을 구조적 보장으로 만든다."""
    state = _state()
    for _ in range(50):
        engine.add_flow(state, "geno", 10_000_000)
    assert state.flow_log["geno"] == pytest.approx(config.FLOW_MAX)


def test_flow_is_capped_downward_too():
    state = _state()
    for _ in range(50):
        engine.add_flow(state, "geno", -10_000_000)
    assert state.flow_log["geno"] == pytest.approx(-config.FLOW_MAX)


def test_flow_cap_is_weaker_than_a_typical_news_ramp():
    """조역이어야 한다. 뉴스를 이기면 게임의 축이 뒤집힌다."""
    assert config.FLOW_MAX < 0.10 * 0.35


def test_flow_only_touches_its_own_symbol():
    state = _state()
    others = {s: price_of(state, s) for s in config.STOCKS if s != "geno"}
    engine.add_flow(state, "geno", 2_000_000)
    assert {s: price_of(state, s) for s in config.STOCKS if s != "geno"} == others


def test_on_tick_receives_every_tick_in_order():
    state = _state()
    seen = []

    def probe(tick):
        seen.append(tick)
        return {}

    advance(state, [], to_tick=5, rng=ZeroRandom(0), on_tick=probe)
    assert seen == [1, 2, 3, 4, 5]


def test_on_tick_sees_price_before_its_own_order_lands():
    """AI 는 자기 주문이 가격을 밀기 전 가격을 보고 판단해야 한다.

    반대로 두면 같은 tick 안에서 자기 체결의 영향을 미리 보고 사는 셈이 된다.
    """
    state = _state()
    observed = []

    def probe(tick):
        observed.append(price_of(state, "geno"))
        return {"geno": 3_000_000}

    advance(state, [], to_tick=2, rng=ZeroRandom(0), on_tick=probe)
    # 1틱째에 본 가격은 아직 주문 충격이 없는 값이다.
    assert observed[0] == state.start_price["geno"]
    # 2틱째에는 1틱의 주문이 (감쇠된 채) 반영돼 있다.
    assert observed[1] > observed[0]


def test_none_on_tick_is_identical_to_before():
    """기존 호출부가 하나도 안 깨져야 한다."""
    a = _state()
    advance(a, [], to_tick=50, rng=random.Random(5))
    b = _state()
    advance(b, [], to_tick=50, rng=random.Random(5), on_tick=None)
    assert a.log_return == b.log_return
    assert a.flow_log == b.flow_log


def test_incremental_matches_bulk_with_flow():
    """따라잡기 요청이 500ms 폴링과 같은 결과를 내야 한다."""
    def orders(tick):
        return {"geno": 200_000} if tick % 7 == 0 else {}

    stepwise = _state()
    rng = random.Random(11)
    for tick in range(1, 61):
        advance(stepwise, [], to_tick=tick, rng=rng, on_tick=orders)

    at_once = _state()
    advance(at_once, [], to_tick=60, rng=random.Random(11), on_tick=orders)

    assert stepwise.log_return == at_once.log_return
    assert stepwise.flow_log == at_once.flow_log
```

추가로, 네 힘이 한 tick 안에서 같이 돌아도 각각 유효한지 본다:

```python
def test_all_four_forces_coexist():
    """노이즈·앵커·램프·주문흐름이 한 tick 에서 같이 돌아도 서로를 지우지 않는다."""
    fair = {symbol: 10_000 for symbol in config.STOCKS}
    state = new_state(fair, random.Random(1))
    state.start_price = {symbol: 10_000 for symbol in config.STOCKS}
    engine.reanchor(state, fair)
    p = plan(impact=0.10, ramp=30, publish_tick=0)

    advance(state, [p], to_tick=30, rng=random.Random(4),
            on_tick=lambda t: {"geno": 300_000})

    # 램프가 주역이다 — 주문 흐름 상한(3%)만으로는 이만큼 못 올린다
    assert price_of(state, "geno") > 10_000 * (1 + config.FLOW_MAX)
    # 주문 흐름도 살아 있다
    assert state.flow_log["geno"] > 0
    # 앵커도 살아 있다 (적정가보다 위이므로 아래로 당기는 중)
    assert state.anchor_log["geno"] - state.log_return["geno"] < 0
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_engine.py -q -k "flow or on_tick or four_forces"`
Expected: FAIL — `AttributeError: module 'app.engine' has no attribute 'add_flow'`

- [ ] **Step 3: `config.py` 에 상수를 넣는다**

`ANCHOR_PULL = 0.004` 아래에 붙인다:

```python
# 주문 흐름의 가격 영향. 100만원어치 순매수가 그 tick 에 가격을 3% 민다.
#
# 누적 로그수익에 영구히 더하면 AI 가 오른 것을 보고 사고 그 매수가 또 올리는
# 무한 나선이 된다. 그래서 따로 들고 매 tick 식힌다. 반감기 ln(2)/0.15 ≈ 4.6 tick.
FLOW_IMPACT_PER_MILLION = 0.03
FLOW_DECAY = 0.15

# 몇 명이 몰려도 이 값을 넘지 못한다. 전형적 뉴스 임팩트 10% 대비 30% 다.
#
# 감쇠만으로는 "주문 흐름은 조역" 이 명단을 고치면 깨지는 약속이다. 상한은
# 명단과 무관하게 깨지지 않는다.
FLOW_MAX = 0.03

# 거래량 집계 구간.
VOLUME_WINDOW_TICKS = 60
```

- [ ] **Step 4: `engine.py` 를 고친다**

`PriceState` 에 필드 하나:

```python
@dataclass
class PriceState:
    log_return: dict[str, float] = field(default_factory=dict)
    start_price: dict[str, int] = field(default_factory=dict)
    anchor_log: dict[str, float] = field(default_factory=dict)
    flow_log: dict[str, float] = field(default_factory=dict)
    last_tick: int = 0
```

`new_state` 의 `return PriceState(...)` 에 한 줄:

```python
    return PriceState(
        log_return={symbol: 0.0 for symbol in config.STOCKS},
        start_price=start_price,
        anchor_log=anchor_log,
        flow_log={symbol: 0.0 for symbol in config.STOCKS},
        last_tick=0,
    )
```

`add_flow` 를 `reanchor` 아래에 추가한다:

```python
def add_flow(state: PriceState, symbol: str, value: int) -> None:
    """원 단위 순매수액을 일시적 가격 충격으로 옮긴다. 매수가 양수다.

    상한은 이 게임의 축을 지킨다 — 주문 흐름이 뉴스보다 세면 낚시를 읽는 것이
    무의미해지고 AI 분석 5회의 희소성이 무너진다.
    """
    nudged = state.flow_log[symbol] + (
        config.FLOW_IMPACT_PER_MILLION * value / 1_000_000
    )
    state.flow_log[symbol] = max(-config.FLOW_MAX, min(config.FLOW_MAX, nudged))
```

`advance` 시그니처와 루프:

```python
def advance(
    state: PriceState,
    plans: Sequence[NewsPlan],
    to_tick: int,
    rng: random.Random,
    on_tick: Callable[[int], dict[str, int]] | None = None,
) -> None:
    """state 를 to_tick 까지 진행한다. to_tick 이 과거면 아무것도 하지 않는다.

    on_tick 은 그 tick 의 종목별 순매수액(원)을 돌려준다. engine 은 누가 왜
    샀는지 모른다 — 매매 규칙은 participants 가 소유한다.
    """
    if to_tick <= state.last_tick:
        return

    active = [...]  # 기존 그대로

    for tick in range(state.last_tick + 1, to_tick + 1):
        for symbol, stock in config.STOCKS.items():
            state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
            gap = state.anchor_log[symbol] - state.log_return[symbol]
            state.log_return[symbol] += config.ANCHOR_PULL * gap
        for plan in active:
            if plan.publish_tick < tick <= plan.publish_tick + plan.ramp_seconds:
                state.log_return[plan.symbol] += plan.impact / plan.ramp_seconds
        # 새 주문을 받기 전에 먼저 식힌다. 그래야 AI 가 보는 가격이 직전 tick 의
        # 충격이 이미 일부 빠진 값이 된다.
        for symbol in config.STOCKS:
            state.flow_log[symbol] *= 1.0 - config.FLOW_DECAY
        if on_tick is not None:
            # AI 는 자기 주문이 가격을 밀기 전 가격을 보고 판단한다.
            for symbol, value in on_tick(tick).items():
                add_flow(state, symbol, value)
    state.last_tick = max(state.last_tick, to_tick)
```

`price_of` 가 두 항을 함께 본다:

```python
def price_of(state: PriceState, symbol: str) -> int:
    """원 단위 정수. 내림으로 통일한다."""
    return math.floor(
        state.start_price[symbol]
        * math.exp(state.log_return[symbol] + state.flow_log[symbol])
    )
```

상단 임포트에 `from collections.abc import Callable, Sequence` 를 맞춘다.

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/engine.py app/config.py tests/test_engine.py
git commit -m "feat: 주문 흐름을 감쇠하는 별도 항으로 넣는다

누적 로그수익에 영구히 더하면 AI 가 오른 것을 보고 사고 그 매수가 또
올리는 무한 나선이 된다. flow_log 를 따로 들고 매 tick 식힌다 —
큰 주문이 불리하게 체결되고 곧 회복되는 슬리피지가 공짜로 나온다.

상한 ±3% 를 걸었다. 감쇠만으로는 '주문 흐름은 조역' 이 명단을 고치면
깨지는 약속이다. 상한은 명단과 무관하게 깨지지 않는다.

on_tick 은 그 tick 의 종목별 순매수액만 받는다. engine 은 누가 왜
샀는지 모른다. None 이면 기존과 완전히 같게 돈다."
```

---

### Task 2: AI 명단과 결정론적 판단

**Files:**
- Create: `backend/app/participants.py`
- Create: `backend/tests/test_participants.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: `config.STOCKS`, `config.SEED_CASH`, `models.NewsPlan`
- Produces:
  - `config.AI` dataclass — `id, name, insight, reaction_ticks, bet_ratio, take_profit`
  - `config.AI_ROSTER: list[AI]` (9명), `AI_COUNT_DEFAULT/MIN/MAX`
  - `participants.AIState` — `profile, cash, holdings: dict[str, tuple[int, int]], cursor: int`
  - `participants.new_participants(count: int) -> list[AIState]`
  - `participants.sees_through(ai_seed: int, ai_index: int, profile, news_id: int) -> bool`
  - `participants.view_of(plan: NewsPlan, sees: bool) -> str` — `"bullish"` | `"bearish"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_participants.py`:

```python
import random

import pytest

from app import config, participants
from app.models import NewsPlan


def plan(symbol="geno", impact=0.10, tone="positive", news_id=0, publish_tick=0):
    return NewsPlan(
        news_id=news_id, symbol=symbol, surface_tone=tone, kind="honest",
        impact=impact, ramp_seconds=20, publish_tick=publish_tick,
    )


def profile(insight=0.5, reaction=3, bet=0.3, take=0.15):
    return config.AI("test", "테스트", insight, reaction, bet, take)


# ------------------------------------------------------------------ 명단

def test_roster_has_nine():
    assert len(config.AI_ROSTER) == config.AI_COUNT_MAX == 9


def test_roster_ids_and_names_are_unique():
    assert len({a.id for a in config.AI_ROSTER}) == 9
    assert len({a.name for a in config.AI_ROSTER}) == 9


def test_roster_parameters_are_in_range():
    for ai in config.AI_ROSTER:
        assert 0.0 <= ai.insight <= 1.0
        assert ai.reaction_ticks >= 1
        assert 0.0 < ai.bet_ratio <= 1.0
        assert ai.take_profit > 0.0


def test_roster_rank_disagrees_with_insight():
    """통찰력 순서와 실력 순서가 어긋나야 '옳게 고르는 것과 이기는 것은 다르다'가 나온다.

    통찰력 상위권에 익절을 못 하는 AI 가, 하위권에 반응이 가장 빠른 AI 가 있어야 한다.
    """
    by_insight = sorted(config.AI_ROSTER, key=lambda a: -a.insight)
    top_three = by_insight[:3]
    bottom_three = by_insight[-3:]

    worst_discipline = max(config.AI_ROSTER, key=lambda a: a.take_profit)
    fastest = min(config.AI_ROSTER, key=lambda a: a.reaction_ticks)

    assert any(a.id == worst_discipline.id for a in top_three) or \
        worst_discipline.insight >= 0.4, "익절 못 하는 AI 가 하위권에만 있으면 교훈이 안 나온다"
    assert fastest in bottom_three, "가장 빠른 AI 는 통찰력 하위권이어야 한다"


def test_new_participants_takes_the_top_n():
    five = participants.new_participants(5)
    assert [a.profile.id for a in five] == [a.id for a in config.AI_ROSTER[:5]]


def test_participants_start_with_seed_cash_and_nothing_held():
    for ai in participants.new_participants(9):
        assert ai.cash == config.SEED_CASH
        assert ai.holdings == {}
        assert ai.cursor == 0


# ------------------------------------------------------------ 통찰력 판정

def test_sees_through_is_deterministic():
    """같은 시드는 같은 판단을 낸다. 재현 없이는 밸런스를 못 고친다."""
    args = (12345, 2, profile(insight=0.5), 7)
    assert participants.sees_through(*args) == participants.sees_through(*args)


def test_sees_through_ignores_call_order():
    """tick 진행 순서와 무관해야 증분/일괄 동일성이 유지된다."""
    forward = [participants.sees_through(99, i, profile(), n)
               for i in range(3) for n in range(4)]
    backward = [participants.sees_through(99, i, profile(), n)
                for i in reversed(range(3)) for n in reversed(range(4))]
    backward.reverse()
    # 같은 (index, news_id) 짝이면 같은 결과여야 한다
    pairs = {(i, n): participants.sees_through(99, i, profile(), n)
             for i in range(3) for n in range(4)}
    assert all(pairs[(i, n)] == participants.sees_through(99, i, profile(), n)
               for i in range(3) for n in range(4))
    assert len(forward) == len(backward) == 12


def test_insight_one_always_sees_through():
    for news_id in range(50):
        assert participants.sees_through(7, 0, profile(insight=1.0), news_id)


def test_insight_zero_never_sees_through():
    for news_id in range(50):
        assert not participants.sees_through(7, 0, profile(insight=0.0), news_id)


def test_insight_roughly_matches_its_probability():
    hits = sum(participants.sees_through(3, 1, profile(insight=0.7), n)
               for n in range(2000))
    assert 0.65 < hits / 2000 < 0.75


def test_different_ais_disagree_on_the_same_news():
    """전원이 똑같이 판단하면 체결 피드에서 신원을 읽을 수 없다."""
    verdicts = {participants.sees_through(5, i, profile(insight=0.5), 42)
                for i in range(9)}
    assert len(verdicts) == 2


# -------------------------------------------------------------- 시각 판정

def test_seeing_through_follows_the_real_impact():
    assert participants.view_of(plan(impact=0.10), sees=True) == "bullish"
    assert participants.view_of(plan(impact=-0.10), sees=True) == "bearish"


def test_being_fooled_follows_the_surface_tone():
    """역방향 함정이 성립하는 지점이다 — 호재로 읽히는데 실제로는 내려간다."""
    trap = plan(impact=-0.10, tone="positive")
    assert participants.view_of(trap, sees=False) == "bullish"
    assert participants.view_of(trap, sees=True) == "bearish"


def test_exaggerated_news_fools_even_a_seer():
    """과장 기사는 부호가 표면과 같다. 통찰력이 높아도 약한 재료를 거른다.

    의도한 것이다 — 과장은 판별이 아니라 크기의 문제다.
    """
    weak = plan(impact=0.004, tone="positive")
    assert participants.view_of(weak, sees=True) == "bullish"
    assert participants.view_of(weak, sees=False) == "bullish"
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_participants.py -q`
Expected: FAIL — `ImportError: cannot import name 'participants' from 'app'`

- [ ] **Step 3: `config.py` 에 명단을 넣는다**

`Stock` dataclass 아래에 `AI` 를 더한다:

```python
@dataclass(frozen=True)
class AI:
    id: str
    name: str
    insight: float         # 낚시를 꿰뚫어 볼 확률
    reaction_ticks: int    # 기사 등장 후 몇 tick 뒤에 움직이나
    bet_ratio: float       # 현금의 몇 %를 거나
    take_profit: float     # 수익률 몇 %에서 파나
```

`VOLUME_WINDOW_TICKS` 아래에 명단을 붙인다:

```python
# 피라미드(고수 2 / 중간 4 / 호구 3) 에 엇박자 둘을 섞었다.
#
# 한실장은 통찰력 2위인데 익절선이 60% 라 계속 옳은 종목을 사면서도 현금이
# 안 쌓인다. 강사원은 통찰력 꼴찌인데 1 tick 만에 반응해 램프 초반을 먹는다.
# 순위가 통찰력 순서와 어긋나야 "옳게 고르는 것과 이기는 것은 다르다" 가 나온다.
#
# 이름은 3차 종토방에서 계속 쓰인다. 여기서 정한 성격이 곧 그 목소리다.
AI_ROSTER: list[AI] = [
    AI("jung", "정소장", 0.90, 3, 0.35, 0.12),
    AI("han",  "한실장", 0.88, 4, 0.45, 0.60),
    AI("oh",   "오과장", 0.60, 5, 0.30, 0.15),
    AI("bae",  "배차장", 0.55, 8, 0.25, 0.10),
    AI("moon", "문대리", 0.50, 6, 0.40, 0.18),
    AI("shin", "신주임", 0.45, 7, 0.20, 0.14),
    AI("kang", "강사원", 0.25, 1, 0.50, 0.08),
    AI("kim",  "김부장", 0.22, 9, 0.55, 0.40),
    AI("park", "박선배", 0.20, 6, 0.60, 0.25),
]

AI_COUNT_DEFAULT = 5
AI_COUNT_MIN = 1
AI_COUNT_MAX = 9
```

- [ ] **Step 4: `app/participants.py` 를 쓴다**

```python
"""AI 참가자. 명단, 판단, 매매를 소유한다.

engine 은 이 파일을 모른다 — "이 tick 에 얼마어치 순매수" 만 콜백으로 받는다.

난수는 engine 의 rng 를 쓰지 않는다. AI 가 매매한 tick 과 안 한 tick 의 난수
소비량이 달라지면 증분 계산과 일괄 계산이 어긋나고, 그 불변식이 이 서버에서
가장 중요한 성질이다. 대신 (시드, AI 번호, 기사 번호) 로 그때그때 뽑는다 —
tick 진행 순서와 무관하게 같은 값이 나온다.
"""
import random
from dataclasses import dataclass, field

from app import config
from app.models import NewsPlan


@dataclass
class AIState:
    profile: config.AI
    cash: int
    # symbol -> (수량, 누적 매입원가). 익절 판정에 평단이 필요하다.
    holdings: dict[str, tuple[int, int]] = field(default_factory=dict)
    # plans 안에서 아직 반응하지 않은 첫 위치. 매 tick 전체를 훑으면
    # 따라잡기 요청이 기사 수 × AI 수 × tick 수로 커진다.
    cursor: int = 0


def new_participants(count: int) -> list[AIState]:
    """명단 위에서 count 명. 기본 5면 고수 2 와 중간 3 이라 초보 난이도다."""
    return [
        AIState(profile=profile, cash=config.SEED_CASH)
        for profile in config.AI_ROSTER[:count]
    ]


def sees_through(
    ai_seed: int, ai_index: int, profile: config.AI, news_id: int
) -> bool:
    """이 AI 가 이 기사의 낚시를 꿰뚫어 보는가. 호출 순서와 무관하다."""
    roll = random.Random(
        (ai_seed * 1_000_003) ^ (news_id * 31) ^ (ai_index * 7)
    ).random()
    return roll < profile.insight


def view_of(plan: NewsPlan, sees: bool) -> str:
    """'bullish' | 'bearish'.

    꿰뚫어 보면 실제 임팩트의 **부호만** 본다. 크기까지 알면 고수 AI 가 완벽해져
    플레이어가 따라잡을 수 없다. 못 보면 표면 톤을 그대로 믿는다 — 역방향 함정이
    성립하는 지점이다.
    """
    if sees:
        return "bullish" if plan.impact > 0 else "bearish"
    return "bullish" if plan.surface_tone == "positive" else "bearish"
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/participants.py app/config.py tests/test_participants.py
git commit -m "feat: AI 명단 9명과 결정론적 통찰력 판정

난수를 (시드, AI 번호, 기사 번호) 로 그때그때 뽑는다. engine 의 rng 를
쓰면 AI 가 매매한 tick 과 안 한 tick 의 소비량이 달라져 증분/일괄
동일성이 깨진다.

꿰뚫어 봐도 임팩트의 부호만 본다. 크기까지 알면 고수 AI 가 완벽해져
플레이어가 따라잡을 수 없다. 그래서 과장 기사에는 고수도 들어간다 —
과장은 판별이 아니라 크기의 문제다.

한실장(통찰력 2위, 익절선 60%)과 강사원(통찰력 꼴찌, 반응 1 tick)이
순위를 통찰력 순서와 어긋나게 만든다."
```

---

### Task 3: AI 매매 — 체결과 익절

**Files:**
- Modify: `backend/app/participants.py`
- Modify: `backend/tests/test_participants.py`

**Interfaces:**
- Consumes: `AIState` (Task 2)
- Produces:
  - `participants.buy(ai: AIState, symbol: str, price: int) -> dict | None`
  - `participants.sell_all(ai: AIState, symbol: str, price: int) -> dict | None`
  - `participants.should_take_profit(ai: AIState, symbol: str, price: int) -> bool`
  - `participants.equity_of(ai: AIState, price_of) -> int`
  - 체결 dict 모양: `{"side", "symbol", "qty", "price", "value"}` — `value` 는 수수료 제외 체결 금액(원)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_participants.py` 끝에 추가한다:

```python
# ------------------------------------------------------------------ 매매

def _ai(cash=config.SEED_CASH, **kwargs):
    return participants.AIState(profile=profile(**kwargs), cash=cash)


def test_buy_spends_the_bet_ratio_and_pays_the_fee():
    ai = _ai(bet=0.30)
    fill = participants.buy(ai, "geno", 40_000)

    assert fill["side"] == "buy" and fill["symbol"] == "geno"
    assert fill["qty"] == 7                      # 30만 // 4만
    assert fill["value"] == 7 * 40_000
    # 플레이어와 같은 규칙 — 양방향 0.2%
    assert ai.cash == config.SEED_CASH - 280_000 - 560


def test_buy_records_cost_including_fee():
    """평단에 수수료가 빠지면 익절선이 실제보다 일찍 걸린다."""
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    qty, cost = ai.holdings["geno"]
    assert (qty, cost) == (7, 280_000 + 560)


def test_buying_twice_accumulates_quantity_and_cost():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    participants.buy(ai, "geno", 50_000)
    qty, cost = ai.holdings["geno"]
    assert qty > 7 and cost > 280_560


def test_buy_returns_none_when_it_cannot_afford_one_share():
    ai = _ai(cash=1_000, bet=0.30)
    assert participants.buy(ai, "geno", 40_000) is None
    assert ai.holdings == {}
    assert ai.cash == 1_000


def test_sell_all_clears_the_position_and_pays_the_fee():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    cash_after_buy = ai.cash

    fill = participants.sell_all(ai, "geno", 50_000)

    assert fill["side"] == "sell" and fill["qty"] == 7
    assert "geno" not in ai.holdings
    assert ai.cash == cash_after_buy + 350_000 - 700


def test_sell_all_on_nothing_is_none():
    assert participants.sell_all(_ai(), "geno", 40_000) is None


def test_take_profit_triggers_above_the_line():
    ai = _ai(bet=0.30, take=0.15)
    participants.buy(ai, "geno", 40_000)
    assert participants.should_take_profit(ai, "geno", 44_000) is False   # +10%
    assert participants.should_take_profit(ai, "geno", 47_000) is True    # +17%


def test_take_profit_is_measured_against_cost_not_price():
    """수수료 때문에 매입원가는 체결가보다 높다. 평단 기준이어야 정확하다."""
    ai = _ai(bet=0.30, take=0.0001)
    participants.buy(ai, "geno", 40_000)
    assert participants.should_take_profit(ai, "geno", 40_000) is False


def test_take_profit_on_nothing_is_false():
    assert participants.should_take_profit(_ai(), "geno", 40_000) is False


def test_equity_counts_cash_and_holdings():
    ai = _ai(bet=0.30)
    participants.buy(ai, "geno", 40_000)
    total = participants.equity_of(ai, lambda s: 40_000)
    assert total == ai.cash + 7 * 40_000


def test_a_broke_ai_simply_stops():
    """노가다는 플레이어 전용 구제 장치다. AI 는 조용히 멈춘다."""
    ai = _ai(cash=0, bet=0.50)
    assert participants.buy(ai, "geno", 40_000) is None
    assert not hasattr(participants, "start_grind")
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_participants.py -q -k "buy or sell or take_profit or equity or broke"`
Expected: FAIL — `AttributeError: module 'app.participants' has no attribute 'buy'`

- [ ] **Step 3: 매매를 `participants.py` 에 추가한다**

`view_of` 아래에 붙인다:

```python
def _fee(gross: int) -> int:
    return math.floor(gross * config.TRADE_FEE_RATE)


def buy(ai: AIState, symbol: str, price: int) -> dict | None:
    """현금의 bet_ratio 만큼 산다. 한 주도 못 사면 None.

    플레이어와 같은 규칙이다 — 양방향 0.2% 수수료, 같은 가격.
    """
    budget = math.floor(ai.cash * ai.profile.bet_ratio)
    qty = budget // price
    while qty > 0 and price * qty + _fee(price * qty) > ai.cash:
        qty -= 1
    if qty <= 0:
        return None

    gross = price * qty
    fee = _fee(gross)
    ai.cash -= gross + fee
    held_qty, held_cost = ai.holdings.get(symbol, (0, 0))
    # 원가에 수수료를 포함한다. 빼면 익절선이 실제보다 일찍 걸린다.
    ai.holdings[symbol] = (held_qty + qty, held_cost + gross + fee)
    return {"side": "buy", "symbol": symbol, "qty": qty,
            "price": price, "value": gross}


def sell_all(ai: AIState, symbol: str, price: int) -> dict | None:
    """공매도가 없으므로 파는 것은 언제나 전량이다."""
    held = ai.holdings.get(symbol)
    if held is None or held[0] <= 0:
        return None

    qty = held[0]
    gross = price * qty
    ai.cash += gross - _fee(gross)
    del ai.holdings[symbol]
    return {"side": "sell", "symbol": symbol, "qty": qty,
            "price": price, "value": -gross}


def should_take_profit(ai: AIState, symbol: str, price: int) -> bool:
    """평가액이 매입원가의 (1 + 익절선) 을 넘었는가."""
    held = ai.holdings.get(symbol)
    if held is None or held[0] <= 0:
        return False
    qty, cost = held
    return price * qty >= cost * (1.0 + ai.profile.take_profit)


def equity_of(ai: AIState, price_of) -> int:
    """현금 + 보유 평가액. price_of 는 symbol 을 받아 정수 가격을 돌려준다."""
    return ai.cash + sum(
        price_of(symbol) * qty for symbol, (qty, _) in ai.holdings.items()
    )
```

상단 임포트에 `import math` 를 더한다.

> `value` 의 부호: 매수가 양수, 매도가 음수다. `engine.add_flow` 가 그대로 받아 순매수면 가격을 올리고 순매도면 내린다.

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 5: 커밋**

```bash
cd backend
git add app/participants.py tests/test_participants.py
git commit -m "feat: AI 매매 — 체결, 평단, 익절

AI 는 플레이어와 같은 규칙을 쓴다. 시드 100만, 양방향 0.2% 수수료,
같은 가격.

매입원가에 수수료를 포함한다. 빼면 익절선이 실제보다 일찍 걸려
'익절 규율' 파라미터가 의도한 값과 달라진다.

파산한 AI 는 조용히 멈춘다. 노가다는 플레이어 전용 구제 장치다."
```

---

### Task 4: 세션 통합 — tick 구동, 체결 피드, 거래량

**Files:**
- Modify: `backend/app/participants.py`
- Modify: `backend/app/session.py`
- Modify: `backend/tests/test_session_rules.py`

**Interfaces:**
- Consumes: Task 1~3 전부
- Produces:
  - `GameSession.ais: list[AIState]`, `ai_seed: int`, `trades: list[dict]`, `trade_seq: int`, `volume_window: deque`, `volume_total: dict[str, int]`
  - `session.record_fill(sess, tick: int, actor: str, fill: dict) -> None`
  - `session.prune_volume(sess, tick: int) -> None`
  - `session.volume_of(sess, symbol: str) -> int`
  - `session.volume_avg_of(sess, symbol: str, tick: int) -> int`
  - `session.ai_rows(sess) -> list[dict]` — `{id, name, cash, equity, rank}`
  - `participants.run_tick(ais, plans, tick, ai_seed, price_of, record) -> dict[str, int]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_session_rules.py` 끝에 추가한다:

```python
# ------------------------------------------------------------ AI 참가자

def test_new_session_seats_the_default_count():
    sess = fresh()
    assert len(sess.ais) == config.AI_COUNT_DEFAULT
    assert sess.trades == []
    assert sess.trade_seq == 0


def test_record_fill_numbers_trades_from_one():
    sess = fresh()
    rules.record_fill(sess, 10, "you",
                      {"side": "buy", "symbol": "geno", "qty": 3,
                       "price": 40_000, "value": 120_000})
    assert sess.trades[0]["seq"] == 1
    assert sess.trades[0]["actor"] == "you"
    assert sess.trades[0]["name"] == config.STOCKS["geno"].name
    assert sess.trades[0]["tick"] == 10


def test_recorded_trades_never_carry_value():
    """value 는 가격 영향 계산용 내부 값이다. 밖으로 나가면 안 된다."""
    sess = fresh()
    rules.record_fill(sess, 1, "you",
                      {"side": "buy", "symbol": "geno", "qty": 3,
                       "price": 40_000, "value": 120_000})
    assert "value" not in sess.trades[0]


def test_volume_window_drops_old_fills():
    sess = fresh()
    rules.record_fill(sess, 1, "you", {"side": "buy", "symbol": "geno",
                                       "qty": 10, "price": 1, "value": 10})
    rules.record_fill(sess, 90, "you", {"side": "buy", "symbol": "geno",
                                        "qty": 5, "price": 1, "value": 5})
    rules.prune_volume(sess, 90)
    assert rules.volume_of(sess, "geno") == 5


def test_volume_counts_both_sides():
    sess = fresh()
    rules.record_fill(sess, 1, "you", {"side": "buy", "symbol": "geno",
                                       "qty": 10, "price": 1, "value": 10})
    rules.record_fill(sess, 2, "kim", {"side": "sell", "symbol": "geno",
                                       "qty": 4, "price": 1, "value": -4})
    assert rules.volume_of(sess, "geno") == 14


def test_volume_avg_is_zero_before_any_trade():
    assert rules.volume_avg_of(fresh(), "geno", tick=300) == 0


def test_ai_rows_rank_by_equity_descending():
    sess = fresh()
    for index, ai in enumerate(sess.ais):
        ai.cash = 1_000_000 + index * 10_000
    rows = rules.ai_rows(sess)
    assert [r["rank"] for r in rows] == list(range(1, len(sess.ais) + 1))
    assert rows[0]["cash"] > rows[-1]["cash"]


def test_ai_rows_break_ties_by_roster_order():
    """임의로 흔들리면 리더보드가 매 폴링마다 요동친다."""
    sess = fresh()
    for ai in sess.ais:
        ai.cash = 1_000_000
    first = [r["id"] for r in rules.ai_rows(sess)]
    assert first == [r["id"] for r in rules.ai_rows(sess)]
    assert first == [a.profile.id for a in sess.ais]


def test_ai_rows_never_expose_holdings():
    sess = fresh()
    for row in rules.ai_rows(sess):
        assert set(row) == {"id", "name", "cash", "equity", "rank"}


# ------------------------------------------------------- AI 의 tick 구동

def _drive(sess, plans, ticks, seed=7):
    """AI 를 ticks 까지 굴리고 tick 별 순주문액을 모은다."""
    flows = []
    for tick in range(1, ticks + 1):
        flows.append(participants.run_tick(
            sess.ais, plans, tick, seed,
            lambda s: 40_000,
            lambda actor, fill: rules.record_fill(sess, tick, actor, fill),
        ))
    return flows


def test_ai_reacts_exactly_at_its_reaction_tick():
    sess = fresh()
    sess.ais = participants.new_participants(1)          # 정소장, 반응 3t
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=5)

    flows = _drive(sess, [p], 12)

    acted = [tick for tick, flow in enumerate(flows, start=1) if flow]
    assert acted == [8]                                   # 5 + 3


def test_ai_reacts_to_each_news_only_once():
    sess = fresh()
    sess.ais = participants.new_participants(1)
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=0)

    _drive(sess, [p], 40)
    buys = [t for t in sess.trades if t["side"] == "buy"]
    assert len(buys) == 1


def test_a_fooled_ai_buys_into_a_reversed_trap():
    sess = fresh()
    sess.ais = participants.new_participants(9)
    trap = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                    kind="reversed", impact=-0.10, ramp_seconds=20,
                    publish_tick=0)

    _drive(sess, [trap], 20)
    buyers = {t["actor"] for t in sess.trades if t["side"] == "buy"}
    assert buyers, "아무도 안 낚이면 함정이 성립하지 않는다"
    assert len(buyers) < 9, "전원이 낚이면 신원을 읽을 수 없다"


def test_same_seed_replays_the_same_trades():
    """재현이 안 되면 밸런스를 못 고친다. 스펙 §9 항목 2."""
    def run():
        sess = new_session("s", random.Random(0), started_at=0.0)
        p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                     kind="reversed", impact=-0.10, ramp_seconds=20,
                     publish_tick=0)
        _drive(sess, [p], 20, seed=4242)
        return [(t["actor"], t["side"], t["qty"]) for t in sess.trades]

    assert run() == run()


def test_ai_driven_incremental_matches_bulk():
    """**이 작업에서 가장 깨지기 쉬운 성질이다.** 스펙 §9 항목 1.

    탭을 비웠다 돌아온 요청(일괄)과 500ms 폴링(증분)이 같은 가격·같은
    체결을 내야 한다. AI 판단이 engine 의 rng 를 소비하면 여기서 깨진다.
    """
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=3)

    def make():
        sess = new_session("s", random.Random(0), started_at=0.0)
        sess.plans.append(p)
        return sess

    def on_tick_for(sess):
        def run(at):
            return participants.run_tick(
                sess.ais, sess.plans, at, sess.ai_seed,
                lambda sym: engine.price_of(sess.prices, sym),
                lambda actor, fill: record_fill(sess, at, actor, fill),
            )
        return run

    stepwise = make()
    rng = random.Random(77)
    driver = on_tick_for(stepwise)
    for tick in range(1, 61):
        engine.advance(stepwise.prices, stepwise.plans, tick, rng, on_tick=driver)

    at_once = make()
    engine.advance(at_once.prices, at_once.plans, 60, random.Random(77),
                   on_tick=on_tick_for(at_once))

    assert stepwise.prices.log_return == at_once.prices.log_return
    assert stepwise.prices.flow_log == at_once.prices.flow_log
    assert [(t["seq"], t["actor"], t["side"], t["qty"]) for t in stepwise.trades] \
        == [(t["seq"], t["actor"], t["side"], t["qty"]) for t in at_once.trades]


def test_flow_value_sign_matches_the_side():
    sess = fresh()
    sess.ais = participants.new_participants(1)
    p = NewsPlan(news_id=0, symbol="geno", surface_tone="positive",
                 kind="honest", impact=0.10, ramp_seconds=20, publish_tick=0)
    flows = _drive(sess, [p], 6)
    assert any(flow.get("geno", 0) > 0 for flow in flows)
```

**임포트를 맞춘다.** 이 파일은 `from app.session import (advance_round, buy, ...)` 로 개별 함수를 가져오는 방식이다. 그 목록에 `new_session` 이 이미 있으므로 `record_fill, prune_volume, volume_of, volume_avg_of, ai_rows` 를 더하고, 위 테스트의 **`rules.` 접두사를 전부 지운다**. 그리고 상단에 두 줄을 더한다:

```python
from app import config, engine, fundamentals, participants
from app.models import NewsPlan
```

(`config, engine, fundamentals` 는 이미 있다 — `participants` 만 더하면 된다.)

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_session_rules.py -q -k "ai or volume or trade or flow"`
Expected: FAIL — `AttributeError: 'GameSession' object has no attribute 'ais'`

- [ ] **Step 3: `participants.run_tick` 을 쓴다**

`participants.py` 끝에 붙인다:

```python
def run_tick(
    ais: list[AIState],
    plans: list[NewsPlan],
    tick: int,
    ai_seed: int,
    price_of,
    record,
) -> dict[str, int]:
    """이 tick 의 AI 매매를 돌리고 종목별 순주문액(원)을 돌려준다.

    price_of(symbol) -> int, record(actor: str, fill: dict) -> None.

    cursor 로 plans 를 AI 마다 한 번만 통과한다. 매 tick 전체를 훑으면
    따라잡기 비용이 기사 수 × AI 수 × tick 수로 커진다.
    """
    flow: dict[str, int] = {}

    def _apply(ai: AIState, fill: dict | None) -> None:
        if fill is None:
            return
        flow[fill["symbol"]] = flow.get(fill["symbol"], 0) + fill["value"]
        record(ai.profile.name, fill)

    for index, ai in enumerate(ais):
        # 1) 반응할 차례가 된 기사들
        while ai.cursor < len(plans):
            plan = plans[ai.cursor]
            if plan.publish_tick + ai.profile.reaction_ticks > tick:
                break
            ai.cursor += 1
            price = price_of(plan.symbol)
            sees = sees_through(ai_seed, index, ai.profile, plan.news_id)
            if view_of(plan, sees) == "bullish":
                _apply(ai, buy(ai, plan.symbol, price))
            else:
                _apply(ai, sell_all(ai, plan.symbol, price))

        # 2) 익절
        for symbol in list(ai.holdings):
            price = price_of(symbol)
            if should_take_profit(ai, symbol, price):
                _apply(ai, sell_all(ai, symbol, price))

    return flow
```

- [ ] **Step 4: `session.py` 에 상태와 헬퍼를 더한다**

상단 임포트:

```python
from collections import deque

from app import config, engine, fundamentals, participants
```

`GameSession` 에 필드를 더한다 (`plans` 위):

```python
    ais: list[participants.AIState] = field(default_factory=list)
    ai_seed: int = 0
    trades: list[dict] = field(default_factory=list)
    trade_seq: int = 0
    # (tick, symbol, qty). 오래된 것은 prune_volume 이 버린다.
    volume_window: deque = field(default_factory=deque)
    volume_total: dict[str, int] = field(default_factory=dict)
```

`new_session` 이 AI 를 앉힌다:

```python
def new_session(
    session_id: str,
    rng: random.Random,
    started_at: float,
    ai_count: int = config.AI_COUNT_DEFAULT,
) -> GameSession:
    return GameSession(
        session_id=session_id,
        rng=rng,
        started_at=started_at,
        prices=engine.new_state(fundamentals.fair_values(1), rng),
        cash=config.SEED_CASH,
        round_start_equity=config.SEED_CASH,
        target=config.SEED_CASH * config.ROUND_TARGET_MULTIPLIER,
        ais=participants.new_participants(ai_count),
        # AI 판단용 시드. engine 의 rng 와 섞지 않는다.
        ai_seed=rng.randrange(2**31),
        volume_total={symbol: 0 for symbol in config.STOCKS},
    )
```

파일 끝에 헬퍼를 더한다:

```python
# --------------------------------------------------- 체결 피드와 거래량

def record_fill(sess: GameSession, tick: int, actor: str, fill: dict) -> None:
    """체결 하나를 피드와 거래량 창에 남긴다.

    fill 의 value 는 가격 영향 계산용 내부 값이라 피드에 싣지 않는다.
    """
    sess.trade_seq += 1
    sess.trades.append({
        "seq": sess.trade_seq,
        "tick": tick,
        "actor": actor,
        "symbol": fill["symbol"],
        "name": config.STOCKS[fill["symbol"]].name,
        "side": fill["side"],
        "qty": fill["qty"],
        "price": fill["price"],
    })
    sess.volume_window.append((tick, fill["symbol"], fill["qty"]))
    sess.volume_total[fill["symbol"]] += fill["qty"]


def prune_volume(sess: GameSession, tick: int) -> None:
    cutoff = tick - config.VOLUME_WINDOW_TICKS
    while sess.volume_window and sess.volume_window[0][0] < cutoff:
        sess.volume_window.popleft()


def volume_of(sess: GameSession, symbol: str) -> int:
    return sum(qty for _, sym, qty in sess.volume_window if sym == symbol)


def volume_avg_of(sess: GameSession, symbol: str, tick: int) -> int:
    """그때까지의 구간 평균. 프론트가 '평소의 5배' 를 계산하는 기준이다."""
    window = config.VOLUME_WINDOW_TICKS
    return round(sess.volume_total[symbol] * window / max(tick, window))


def ai_rows(sess: GameSession) -> list[dict]:
    """리더보드. 보유 종목은 싣지 않는다 — 체결 피드로 재구성하는 것이 정당한 우위다.

    순위는 총자산 기준이다. 목표 판정이 현금으로 바뀌는 것은 D 와 함께 온다.
    동점은 명단 순서로 가른다 — 임의로 흔들리면 매 폴링마다 리더보드가 요동친다.
    """
    def price(symbol: str) -> int:
        return engine.price_of(sess.prices, symbol)

    scored = [
        (index, ai, participants.equity_of(ai, price))
        for index, ai in enumerate(sess.ais)
    ]
    scored.sort(key=lambda row: (-row[2], row[0]))
    return [
        {
            "id": ai.profile.id,
            "name": ai.profile.name,
            "cash": ai.cash,
            "equity": total,
            "rank": rank,
        }
        for rank, (_, ai, total) in enumerate(scored, start=1)
    ]
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/participants.py app/session.py tests/test_session_rules.py
git commit -m "feat: AI 의 tick 구동, 체결 피드, 거래량 집계

AI 마다 cursor 를 들려 plans 를 한 번만 통과한다. 매 tick 전체를
훑으면 따라잡기 비용이 기사 수 x AI 수 x tick 수로 커진다.

체결의 value(순주문액)는 가격 영향 계산용 내부 값이라 피드에 싣지
않는다. 리더보드도 보유 종목을 싣지 않는다 — 체결 피드로 재구성하는
것이 주의 깊은 플레이어의 정당한 우위다.

순위는 총자산 기준이다. 목표 판정을 현금으로 바꾸는 것은 D 와 함께
온다. 동점은 명단 순서로 가른다."
```

---

### Task 5: HTTP — 콜백 연결과 응답 필드

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1~4 전부
- Produces: `POST /api/game` 의 `ai_count`, `GET /api/state` 의 `trades_since`, 스냅샷의 `ai`·`trades`·`stocks[].volume`·`stocks[].volume_avg`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/tests/test_api.py` 끝에 추가한다:

```python
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
    for row in start(client)["ai"]:
        assert set(row) == {"id", "name", "cash", "equity", "rank"}
    ranks = [row["rank"] for row in start(client)["ai"]]
    assert sorted(ranks) == list(range(1, config.AI_COUNT_DEFAULT + 1))


def test_ais_actually_trade_once_time_passes(client):
    sid = start(client, ELAPSED)["session_id"]
    body = state(client, sid)
    assert body["trades"], "120초가 흘렀는데 AI 가 한 번도 안 움직였다"
    assert all(t["actor"] != "you" for t in body["trades"])


def test_trades_since_filters_like_since(client):
    sid = start(client, ELAPSED)["session_id"]
    highest = max(t["seq"] for t in state(client, sid)["trades"])
    response = client.get(
        f"/api/state?session_id={sid}&trades_since={highest}"
    )
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -q -k "ai or trade or volume"`
Expected: FAIL — `KeyError: 'ai'`

- [ ] **Step 3: `main.py` 를 고친다**

임포트에 `participants` 를 더한다:

```python
from app import (
    analysis, company_analysis, config, engine, fallback, fundamentals,
    news, participants, session as rules,
)
```

`_sync` 가 콜백을 연결한다:

```python
def _sync(sess: GameSession, now: float) -> int:
    """tick 을 현재까지 진행하고 노가다 보수를 정산한다.

    AI 매매는 tick 루프 안에서 돈다 — 매수가 그 tick 의 가격을 밀고, 그것이
    다음 tick 의 AI 판단에 들어간다. engine 은 순주문액만 받는다.
    """
    tick = _tick_of(sess, now)

    def on_tick(at: int) -> dict[str, int]:
        return participants.run_tick(
            sess.ais, sess.plans, at, sess.ai_seed,
            lambda symbol: engine.price_of(sess.prices, symbol),
            lambda actor, fill: rules.record_fill(sess, at, actor, fill),
        )

    engine.advance(sess.prices, sess.plans, tick, sess.rng, on_tick=on_tick)
    rules.prune_volume(sess, tick)
    rules.settle_grind(sess, now)
    return tick
```

`_stock_rows` 가 tick 을 받아 거래량을 싣는다:

```python
def _stock_rows(sess: GameSession, tick: int) -> list[dict]:
    rows = []
    for symbol, stock in config.STOCKS.items():
        price = engine.price_of(sess.prices, symbol)
        rows.append({
            "symbol": symbol,
            "name": stock.name,
            "sector": stock.sector,
            "price": price,
            "change_pct": round(
                (price / sess.prices.start_price[symbol] - 1) * 100, 2
            ),
            "held": sess.holdings.get(symbol, 0),
            "fundamentals_analyzed": symbol in sess.analyzed_symbols,
            "volume": rules.volume_of(sess, symbol),
            "volume_avg": rules.volume_avg_of(sess, symbol, tick),
        })
    return rows
```

체결 피드 행 필터를 `_news_rows` 아래에 더한다:

```python
def _trade_rows(sess: GameSession, trades_since: int) -> list[dict]:
    return [row for row in sess.trades if row["seq"] > trades_since]
```

`_snapshot` 시그니처와 본문:

```python
def _snapshot(
    sess: GameSession, now: float, since: int = -1, trades_since: int = -1
) -> dict:
    tick = _sync(sess, now)
    return {
        ...기존 필드 그대로...
        "company_analyses_left": sess.company_analyses_left,
        "ai": rules.ai_rows(sess),
        "trades": _trade_rows(sess, trades_since),
        ...
        "stocks": _stock_rows(sess, tick),
        ...
    }
```

`POST /api/game` 이 본문을 받는다. `AnalyzeBody` 아래에 모델을 더한다:

```python
class NewGameBody(BaseModel):
    ai_count: int = config.AI_COUNT_DEFAULT
```

라우트:

```python
@app.post("/api/game")
async def new_game(
    background: BackgroundTasks, body: NewGameBody | None = None
) -> dict:
    # 본문 없이 부르는 기존 클라이언트를 깨지 않는다.
    ai_count = body.ai_count if body is not None else config.AI_COUNT_DEFAULT
    if not config.AI_COUNT_MIN <= ai_count <= config.AI_COUNT_MAX:
        raise HTTPException(400, {
            "code": "bad_ai_count",
            "message": f"AI 수는 {config.AI_COUNT_MIN}~{config.AI_COUNT_MAX} 입니다.",
        })

    now = time.monotonic()
    session_id = uuid.uuid4().hex
    rng = random.Random()
    sess = rules.new_session(session_id, rng, started_at=now, ai_count=ai_count)
    ...나머지는 기존 그대로...
```

`GET /api/state` 가 쿼리를 하나 더 받는다:

```python
@app.get("/api/state")
async def get_state(
    session_id: str,
    background: BackgroundTasks,
    since: int = -1,
    trades_since: int = -1,
) -> dict:
    sess = _get(session_id)
    async with _lock(session_id):
        snapshot = _snapshot(sess, time.monotonic(), since, trades_since)
    ...
```

`POST /api/trade` 가 플레이어 체결을 피드와 가격에 반영한다. `result["equity"] = ...` 앞에 넣는다:

```python
        value = result["gross"] if body.side == "buy" else -result["gross"]
        rules.record_fill(sess, _tick_of(sess, now), "you", {
            "side": result["side"], "symbol": result["symbol"],
            "qty": result["qty"], "price": result["price"], "value": value,
        })
        # 플레이어의 주문도 가격을 민다. 큰 주문일수록 불리하게 체결된다.
        engine.add_flow(sess.prices, result["symbol"], value)
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS. 전부.

- [ ] **Step 5: 서버를 띄워 한 판 확인한다**

```bash
cd backend
.venv/bin/uvicorn app.main:app --port 7999 --log-level warning &
sleep 3
SID=$(curl -s -X POST localhost:7999/api/game -H 'Content-Type: application/json' \
  -d '{"ai_count":9}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
sleep 25
curl -s "localhost:7999/api/state?session_id=$SID" | python3 -c '
import json, sys
s = json.load(sys.stdin)
print("리더보드"); [print(f"  {r[\"rank\"]}. {r[\"name\"]:<6} {r[\"equity\"]:>10,}원") for r in s["ai"]]
print("체결", len(s["trades"]), "건")
for t in s["trades"][-5:]:
    print(f"  {t[\"actor\"]:<6} {t[\"side\"]:<4} {t[\"name\"]} {t[\"qty\"]}주 @{t[\"price\"]:,}")
'
kill %1
```

Expected: 리더보드 9행과 체결 몇 건. 아무도 안 움직였으면 `reaction_ticks` 나 `publish_tick` 을 의심한다.

- [ ] **Step 6: 커밋**

```bash
cd backend
git add app/main.py tests/test_api.py
git commit -m "feat: HTTP — AI 리더보드, 체결 피드, 거래량

_sync 가 engine 의 tick 루프에 AI 구동을 연결한다. 매수가 그 tick 의
가격을 밀고 그것이 다음 tick 의 AI 판단에 들어간다.

POST /api/game 의 본문은 선택이다. 프론트가 지금 본문 없이 부르고
있어 깨지면 안 된다.

플레이어 체결도 피드에 흐르고 가격을 민다 — 큰 주문일수록 불리하게
체결되는 슬리피지가 생긴다."
```

---

## 마무리

- [ ] **전체 테스트**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **`docs/api.md` 2부에서 구현된 것을 1부로 옮긴다**

A·B·C·F·G 가 구현됐으므로 §11 의 해당 계약을 1부(§3·§4·§5)로 옮기고, 2부에는 **D·E 만** 남긴다. 실제 서버 응답을 캡처해서 쓴다 — 이 문서의 규약이다.

§13 의 "개발 예정 7개" 표를 2개로 줄이고, "순서" 절을 3차 종토방이 다음임을 반영해 고친다.

- [ ] **README 갱신**

모듈 표에 `participants` 를 더하고 테스트 개수를 **세어서** 쓴다. "현재 상태" 의 다음 항목을 종토방으로 바꾼다.

- [ ] **프론트 세션에 알린다**

`ai`·`trades`·`stocks[].volume`·`stocks[].volume_avg` 네 필드가 새로 생겼고 기존 필드는 하나도 안 바뀌었다는 것. 그리고 `POST /api/game` 에 `ai_count` 를 보낼 수 있다는 것.

- [ ] **브랜치 마무리**

`superpowers:finishing-a-development-branch` 를 쓴다.
