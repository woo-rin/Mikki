# 펀더멘털 앵커와 기업분석 설계

작성일: 2026-09-14 · 대상: 1차 (3단계 중 첫째)

## 1. 왜 이걸 만드나

받은 피드백 세 가지에서 출발한다.

| | 피드백 | 이 설계가 답하는 방식 |
|---|---|---|
| ① | 도메인에 대한 이해 | 실존 기업의 실제 재무를 게임 규칙에 **직접** 연결한다 |
| ② | 종토방 추가 | 이 문서 밖. 3차에서 다룬다 (§8) |
| ③ | 가치 판단은 어떻게? → 오픈 API 로 실제 종목 | 실제 재무로 **적정가**를 만들고 가격이 거기로 끌린다 |

지금 게임에는 가치 판단이 없다. 플레이어가 답해야 하는 질문이 *"이 기사가 진짜인가"* 하나뿐이고, 종목 자체는 뉴스가 붙는 껍데기다. 6종목의 `base_price` 는 고정 상수라서 두 번째 판부터는 외운 숫자가 된다.

이 설계는 **두 번째 축**을 넣는다. 뉴스 축이 *"이 기사가 진짜인가"* 를 묻고, 펀더멘털 축이 *"이 회사가 애초에 좋은가"* 를 묻는다. 둘 다 답해야 이긴다.

## 2. 핵심 설계 원칙

기존 4개 원칙(설계 스펙 §1)을 그대로 승계하고 세 개를 더한다.

5. **실제 데이터, 가상 이름.** 실존 기업의 재무를 쓰되 이름은 지금의 가상 6종목을 유지한다. 실명을 쓰면 `scenario` 가 만드는 역방향 함정이 **실존 기업에 대한 허위 악재**가 된다. 스크린샷 한 장이 게임 밖으로 나가면 맥락이 사라진다. 데이터가 진짜면 도메인 이해는 그대로 드러나고, 리스크는 0 이다.
6. **런타임에 외부 API 를 부르지 않는다.** 재무는 분기에 한 번 바뀌고 게임 한 판은 몇 분이다. 실시간 호출은 구조적으로 이유가 없다. 스냅샷을 떠서 커밋하고 서버는 파일만 읽는다. 테스트 122개가 네트워크도 Claude 도 안 부르는 성질을 지킨다.
7. **적정가도 정답이다.** 임팩트와 똑같이 서버 안에만 두고, 기업분석을 지불해야 얻는다.

## 3. 데이터

### 스냅샷 파일

`backend/data/fundamentals.json` — 커밋한다. 서버는 읽기만 한다.

```json
{
  "generated_at": "2026-09-14",
  "source": "DART 오픈API (fnlttSinglAcntAll, stockTotqySttus)",
  "stocks": {
    "geno": {
      "mapped_from": "실존 바이오 중형주",
      "quarters": [
        {
          "label": "2024Q1",
          "revenue": 81200000000,
          "operating_income": 16500000000,
          "net_income": 12800000000,
          "equity": 240000000000,
          "debt": 96000000000,
          "shares": 12400000
        }
      ]
    }
  }
}
```

- 6종목 전부, 분기 **최소 4개**. 라운드 N 이 `quarters[N-1]` 을 쓴다.
- 분기가 모자라면 마지막 분기를 계속 쓴다. 라운드 수에 상한이 없기 때문이다.
- `mapped_from` 은 사람이 읽는 설명 문자열이다. **종목 코드나 `corp_code` 를 넣지 않는다** — 넣으면 매핑이 역추적되어 원칙 5가 무너진다.

### 갱신 스크립트

`backend/scripts/fetch_fundamentals.py` — **서버가 임포트하지 않는다.** 분기마다 손으로 돌린다.

```bash
DART_API_KEY=... python3 scripts/fetch_fundamentals.py
```

- `fnlttSinglAcntAll.json` 에서 손익·재무상태, `stockTotqySttus.json` 에서 주식총수를 받는다.
- 매핑표(가상 심볼 → 실존 `corp_code`)는 **스크립트 안에만** 둔다. 출력 JSON 에는 넣지 않는다.
- 실패하면 기존 파일을 덮어쓰지 않고 죽는다. 반쪽 스냅샷이 커밋되는 것보다 낫다.

## 4. 적정가

새 모듈 `app/fundamentals.py` 가 소유한다.

```
EPS  = 당기순이익 / 주식수
적정가 = 섹터 기준 PER × EPS
```

**적자면 PER 이 의미를 잃는다.** 바이오는 적자가 흔하고, 음수 EPS 는 음수 적정가를 낳는다. 순이익이 0 이하면 매출 기준으로 떨어진다:

```
SPS  = 매출액 / 주식수
적정가 = 섹터 기준 PSR × SPS
```

적자 성장주를 PSR 로 보는 것은 실제 밸류에이션 실무와 같다. 회피가 아니라 도메인이다.

섹터 기준 배수는 `config` 상수다. 실제 시장 평균에서 따오되, 밸런스 손잡이로 쓴다.

| 섹터 | 기준 PER | 기준 PSR |
|---|---|---|
| 반도체 | 14.0 | 2.2 |
| 바이오 | 38.0 | 6.5 |
| 2차전지 | 22.0 | 2.8 |
| 게임 | 16.0 | 3.0 |
| 건설 | 7.5 | 0.5 |
| 항공 | 11.0 | 1.1 |

적정가는 원 단위 정수로 내림한다 — 돈은 전부 내림이라는 기존 규칙 그대로다.

## 5. 시작 오프셋 — `base_price` 를 없앤다

**이 설계의 알맹이다.**

지금 `config.Stock.base_price` 는 고정 상수다. 적정가를 얹기만 하면 어느 종목이 고평가인지가 매판 똑같고, 한 번 외운 플레이어에게 기업분석은 죽은 기능이 된다.

그래서 `base_price` 를 `config` 에서 **제거하고**, 게임 시작 때 각 종목을 적정가 대비 랜덤 위치에 놓는다.

```python
offset      = rng.uniform(-0.30, 0.30)          # START_OFFSET_RANGE
start_price = floor(fair_value * (1 + offset))
```

매판 어느 종목이 고평가인지 달라진다. 기업분석을 사야 할 이유가 매판 새로 생긴다.

### 파급

`base_price` 를 읽는 곳이 셋이다. 전부 세션 상태를 보게 바꾼다.

| 위치 | 지금 | 바뀐 뒤 |
|---|---|---|
| `engine.price_of` | `config.STOCKS[s].base_price` | `state.start_price[s]` |
| `main._stock_rows` 의 `change_pct` | `price / stock.base_price - 1` | `price / state.start_price[s] - 1` |
| `engine.new_state()` | 인자 없음 | `new_state(fair_values, rng)` |

`PriceState` 가 두 필드를 얻는다:

```python
@dataclass
class PriceState:
    log_return: dict[str, float]
    start_price: dict[str, int]     # 판마다 다르다. 게임 내내 고정
    anchor_log: dict[str, float]    # 시작가 대비 적정가의 로그거리
    last_tick: int = 0
```

기존 주석이 말하는 성질 — *"정수 시작가는 정확히 남기고 수익률만 float 로 둔다"* — 은 그대로 지킨다. `start_price` 가 정수이고 `log_return` 이 0 에서 출발하므로 첫 tick 의 가격은 정확히 시작가다.

## 6. 앵커 — 엔진에 항 하나

`engine.advance()` 의 tick 루프에 평균회귀를 더한다.

```python
for tick in range(state.last_tick + 1, to_tick + 1):
    for symbol, stock in config.STOCKS.items():
        state.log_return[symbol] += stock.volatility * rng.gauss(0.0, 1.0)
        gap = state.anchor_log[symbol] - state.log_return[symbol]
        state.log_return[symbol] += config.ANCHOR_PULL * gap
    for plan in active:
        ...  # 뉴스 램프는 지금 그대로
```

표준 Ornstein–Uhlenbeck 회귀다. `gap` 이 적정가까지 남은 로그거리이므로 힘은 **항상 적정가 쪽**이고, 가까워질수록 약해진다.

### 강도

`ANCHOR_PULL = 0.004` 에서 시작한다. 반감기가 `ln(2) / 0.004 ≈ 173` tick ≈ 2분 53초다.

뉴스 램프와 대비하면 의도가 분명해진다:

| | 시간 규모 | tick 당 기여 (최대 괴리 기준) |
|---|---|---|
| 뉴스 램프 | 15~40초 | 0.12% ~ 1.0% |
| 앵커 | 약 3분 | 0.10% (30% 괴리에서) |
| 노이즈 | — | 0.15% ~ 0.40% |

앵커는 단일 tick 에서 노이즈보다 작아 **즉시 눈에 띄지 않는다.** 대신 방향이 일정해서 누적되면 이긴다. 그래야 *"호재는 진짜였는데 램프가 끝나니 도로 끌려 내려간다"* 가 나온다. 두 축이 싸우는 그림이 이 설계가 노리는 것이다.

**앵커는 절대 뉴스를 이기면 안 된다.** 이기면 뉴스가 장식이 되고 AI 분석 5회의 희소성이 무너진다. `ANCHOR_PULL` 을 올릴 때 이것이 상한이다.

### 순서가 결정론에 미치는 영향

난수는 종목 루프에서만 소비된다. 앵커는 난수를 쓰지 않으므로 **증분 계산과 일괄 계산이 여전히 같은 결과를 낸다.** 기존 `engine` 의 핵심 불변식이 유지된다. 테스트로 못박는다.

## 7. 기업분석 — 두 번째 유료 행동

### 계약

```
POST /api/company-analysis    { session_id, symbol }
```

```json
{
  "symbol": "geno",
  "name": "제노셀",
  "fair_value": 39216,
  "current_price": 45100,
  "gap_pct": 15.0,
  "valuation": "overvalued",
  "label": "고평가",
  "financials": {
    "quarter": "2024Q1", "revenue": 81200000000,
    "operating_income": 16500000000, "net_income": 12800000000,
    "eps": 1032, "per": 43.7, "debt_ratio": 40.0
  },
  "commentary": "...",
  "offline": false,
  "company_analyses_left": 1
}
```

`app/analysis.py` 와 **정확히 대칭**이다. 서버가 쥔 확정 판정을 돈 주고 사고, Claude 는 근거만 풀어쓴다. 원칙 3(*Claude 는 판정자가 아니라 해설자다*)이 그대로 적용된다 — `valuation` 은 서버가 정하고 Claude 에게는 확정값을 전부 넘긴다.

`main.analyze` 의 **락 패턴을 그대로 따른다**: 차감까지만 락 안에서, Claude 호출은 락 밖에서. 락을 쥔 채 기다리면 같은 세션의 `/api/state` 폴링이 멈춰 시장이 얼어붙는다.

### 등급

`gap_pct = (current_price − fair_value) / fair_value × 100` (양수 = 고평가)

| gap_pct | valuation | label |
|---|---|---|
| ≥ +25 | `severely_overvalued` | 심각한 고평가 |
| +25 ~ +10 | `overvalued` | 고평가 |
| +10 ~ −10 | `fair` | 적정 |
| −10 ~ −25 | `undervalued` | 저평가 |
| ≤ −25 | `severely_undervalued` | 심각한 저평가 |

AI 분석의 5단계 강도와 대칭이다. 시작 오프셋이 ±30% 이고 라운드 중 가격이 움직이므로 다섯 구간이 전부 나온다.

### 횟수

`COMPANY_ANALYSES_PER_ROUND = 2`. AI 분석 5회와 **별개 풀**이고 라운드 전환 때 함께 리필된다.

5회가 아닌 이유: 재무는 라운드 내내 안 바뀌므로 한 번 사면 그 라운드 끝까지 유효하다. 종목이 6개인데 5회면 사실상 전부 볼 수 있어서 선택이 사라진다. 2회면 **"어느 종목의 적정가를 살 것인가"** 가 결정이 된다.

### 폴백

키가 없거나 호출이 실패하면 `fallback` 이 등급과 재무 수치에서 템플릿 해설을 만든다. 기존 `fallback.explain_*` 과 같은 모양이고, `offline: true` 로 표시한다. **게임은 멈추지 않는다.**

## 8. 라운드와 분기

라운드 N → `quarters[N-1]`. 라운드가 넘어가면 새 실적이 반영돼 적정가가 움직인다.

`advance_round` 가 하는 일이 늘어난다:

```python
sess.round_no += 1
...
sess.analyses_left = config.ANALYSES_PER_ROUND
sess.company_analyses_left = config.COMPANY_ANALYSES_PER_ROUND
_reanchor(sess)      # 새 분기 재무 → 새 적정가 → anchor_log 갱신
```

**시작 오프셋을 다시 뽑지 않는다.** `start_price` 는 게임 내내 고정이고 `anchor_log` 만 바뀐다. 가격이 점프하면 플레이어가 들고 있던 종목의 평가액이 순간이동한다.

효과는 이렇다 — 지난 라운드에 산 적정가 정보가 **낡는다.** 실적이 좋아진 회사는 저평가로 바뀌고 나빠진 회사는 고평가가 된다. 라운드 전환에 지금 없는 의미가 생긴다.

## 9. 상태 응답 변경

`_snapshot` 에 한 줄, `_stock_rows` 에 한 줄.

```json
{ "company_analyses_left": 2,
  "stocks": [ { "symbol": "geno", "...": "...", "fundamentals_analyzed": false } ] }
```

- `company_analyses_left` — 남은 기업분석 횟수
- `stocks[].fundamentals_analyzed` — 이 라운드에 이 종목의 적정가를 샀는지. 프론트가 배지를 그린다.
  뉴스의 `analyzed` 와 이름을 다르게 둔다 — 둘은 다른 자원이고 같은 이름이면 프론트가 헷갈린다

**`fair_value` 와 `valuation` 은 스냅샷에 넣지 않는다.** 원칙 7이다. 기업분석 응답으로만 나간다. 프론트는 그 응답을 받아 들고 있어야 하고, 새로고침하면 사라진다 — 지금 AI 분석 결과와 같은 성질이다.

## 10. 만져야 하는 것

| 파일 | 무엇 | 신규 |
|---|---|---|
| `data/fundamentals.json` | 스냅샷 | ● |
| `scripts/fetch_fundamentals.py` | DART 호출. 서버는 안 씀 | ● |
| `app/fundamentals.py` | 스냅샷 로딩, 적정가 계산, 등급 판정 | ● |
| `app/company_analysis.py` | Claude 해설 (`analysis.py` 와 쌍) | ● |
| `app/engine.py` | 앵커 항, `PriceState` 확장, `new_state` 시그니처 | |
| `app/config.py` | `base_price` 제거, 섹터 배수·`ANCHOR_PULL`·오프셋 범위 | |
| `app/session.py` | `company_analyses_left`, `spend_company_analysis`, 라운드 재앵커 | |
| `app/main.py` | 새 엔드포인트, 스냅샷 2필드, `change_pct` 기준 변경 | |
| `app/fallback.py` | 기업분석 폴백 해설 | |

## 11. 테스트

**네트워크도 Claude 도 부르지 않는다.** 기존 122개의 성질을 그대로 지킨다. 스냅샷은 파일이고 테스트는 고정 픽스처를 쓴다.

새 파일 `tests/test_fundamentals.py`, `tests/test_company_analysis.py`. 기존 파일에도 추가한다.

지켜야 할 것:

| | 무엇 | 어디 |
|---|---|---|
| 1 | EPS·PER 계산이 정확하다 | `test_fundamentals` |
| 2 | 순이익 ≤ 0 이면 PSR 로 떨어진다 | `test_fundamentals` |
| 3 | 적정가가 원 단위 정수로 내림된다 | `test_fundamentals` |
| 4 | 등급 경계값 5구간이 정확하다 (±10, ±25) | `test_fundamentals` |
| 5 | 시작 오프셋이 같은 시드에서 결정론적이다 | `test_engine` |
| 6 | 앵커가 가격을 **적정가 쪽으로만** 민다 (양쪽 다) | `test_engine` |
| 7 | 앵커만 있을 때 가격이 적정가로 수렴한다 | `test_engine` |
| 8 | 증분 계산과 일괄 계산이 여전히 같다 | `test_engine` (기존 확장) |
| 9 | 램프가 끝난 뒤 앵커가 되돌린다 | `test_engine` |
| 10 | 기업분석 차감, 소진 시 오류, 라운드 리필 | `test_session_rules` |
| 11 | 라운드 전환이 적정가만 바꾸고 가격은 안 건드린다 | `test_session_rules` |
| 12 | 스냅샷에 `fair_value`/`valuation` 이 **없다** | `test_api` |
| 13 | 분기가 모자라면 마지막 분기를 쓴다 | `test_fundamentals` |
| 14 | 폴백 해설이 키 없이 나온다 | `test_company_analysis` |
| 15 | 기업분석 중 락을 쥐지 않는다 | `test_api` (기존 패턴) |

12번이 특히 중요하다. 원칙 7이 깨지면 F12 한 번으로 기업분석이 무의미해진다. 기존 `test_api` 가 `impact`/`kind` 누출을 막는 것과 같은 방식으로 못박는다.

## 12. 이 문서 밖 — 2차와 3차

의존성 때문에 순서가 정해져 있다.

```
1차  펀더멘털 + 기업분석   ← 이 문서
      ↓  AI 성향에 "재무를 보는가" 축이 생긴다
2차  AI 참가자             v2 설계(api.md §13)의 A
      ↓  AI 의 포지션·성향에서 글이 나온다
3차  종토방                여론 = 세 번째 정보 레이어
```

종토방은 **AI 참가자가 쓴다.** 플레이어가 쓰는 진짜 게시판은 DB·계정·영속성이 따라오고, 지금 세션이 전부 메모리에 있으므로 서버 구조가 통째로 바뀐다. AI 가 쓰면 싱글플레이어 그대로 두고도 *믿을 수 없는 군중* 이라는 층이 생긴다 — 뉴스가 믿을 수 없는 기사인 것과 짝이 맞는다.

각 차수는 자기 스펙과 계획을 따로 갖는다. 셋을 한 문서에 몰면 계획서가 감당이 안 된다.

## 13. 결정하지 않은 것

여기 있는 숫자는 **플레이해보며 조정한다.** 지금 값은 근거 있는 출발점이지 확정이 아니다.

1. `ANCHOR_PULL = 0.004` — 앵커가 체감되지 않으면 올리고, 뉴스를 덮으면 내린다. 상한은 §6 의 규칙이다
2. `START_OFFSET_RANGE = (-0.30, 0.30)` — 좁히면 기업분석이 시시해지고, 넓히면 뉴스 축이 묻힌다
3. `COMPANY_ANALYSES_PER_ROUND = 2` — 6종목 대비 선택이 생기는 최대치가 2~3 이다
4. 섹터 기준 배수 6쌍 — 실제 시장 평균에서 따오되 밸런스 손잡이로 쓴다
5. 어느 실존 기업을 어느 심볼에 매핑할지 — 섹터가 맞고 분기 4개가 온전한 곳을 고른다. 적자 분기가 하나쯤 섞이면 오히려 좋다 (PSR 경로가 실제로 쓰인다)
