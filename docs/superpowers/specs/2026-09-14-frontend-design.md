# 프론트엔드 설계 — 1부 현행 계약

작성일: 2026-09-14 · 대상 백엔드: `docs/api.md` **1부(§0~§08)** · 기준 커밋 `56159d9`

## 0. 이 문서의 범위

**안에 있는 것** — 기술 스택, 프로젝트 구조, API 계층, 상태 구조, 기능 명세 11개,
개발 환경, 테스트 전략.

**밖에 있는 것** — 세 가지다.

| 밖 | 왜 |
|---|---|
| 미학 방향 | `design/` 의 A·B·C 가 아직 미선택이다. 고른 뒤 별도 라운드에서 다룬다. 이 문서는 **무엇을 보여주는가**만 정하고 **어떻게 생겼는가**는 정하지 않는다 |
| 펀더멘털 앵커 (1차) | `2026-09-14-fundamentals-anchor-design.md`. 스냅샷에 `company_analyses_left` 와 `stocks[].fundamentals_analyzed` 가 붙는다 |
| AI 참가자·종토방 (2·3차) | `api.md` 2부. 리더보드·체결 피드·거래량이 새로 생긴다 |

`api.md` §13 "순서" 는 프론트를 먼저 만들면 두 번 만들게 된다고 경고한다. 그 경고를 받아들이되,
**두 번째 제작 비용이 `api/types.ts` 한 파일과 새 컴포넌트로 국한되도록** 계층을 그었다(§2 원칙 2).

## 1. 결정 사항

| | 결정 | 왜 |
|---|---|---|
| 타깃 계약 | `api.md` 1부만 | 지금 122개 테스트가 지키는 계약이다. 한 판을 끝까지 플레이할 수 있는 화면을 먼저 완성한다 |
| 프레임워크 | **React + TypeScript + Vite** | 단일 화면·SEO 무관·백엔드 별도라 SSR 이 쓰일 곳이 없다. Next.js 는 서버 계층을 둘로 만든다 |
| 상태 | **Zustand 두 스토어 + 단일 폴링 훅** | 서버가 준 것과 내가 쌓은 것의 경계가 이 앱의 중심축이다(§2 원칙 1). 셀렉터 구독으로 500ms 전체 리렌더를 막는다 |
| 차트 | **손으로 그린 SVG** | 60틱 라인 + 뉴스 마커 + 램프 밴드는 차트 라이브러리가 잘 못 하는 조합이다. `api.md` §8 도 "그림은 전부 프론트가 SVG 로" 라고 못박았다 |
| 테스트 | **Vitest + Testing Library + MSW** | 백엔드 122개가 네트워크도 Claude 도 안 부르는 성질을 프론트도 그대로 가져간다 |
| 개발 연결 | **Vite `/api` 프록시 → `:7999`** | 백엔드에 CORS 미들웨어가 **없다**. 프록시를 쓰면 백엔드를 한 줄도 안 건드린다 |
| 배포 | **`build` 산출물 → `backend/static/`** | `backend/app/main.py:327` 이 `os.path.isdir("static")` 일 때 `/` 에 마운트한다. 이미 열려 있는 출구다 |
| 패키지 매니저 | **npm** | 레포에 다른 JS 프로젝트가 없어 워크스페이스 이점이 없다. Node v22.17.1 / npm 10.9.2 확인 |
| 대상 화면 | **데스크톱, 최소 폭 1280** | 목업이 MacBook 1440×900 이다. 모바일은 지원하지 않는다고 명시해 범위를 닫는다 |

## 2. 설계 원칙

백엔드 설계 스펙의 원칙을 승계하고, 프론트에만 해당하는 다섯 개를 둔다.

1. **서버가 준 것과 내가 쌓은 것을 섞지 않는다.** 스토어 파일 두 개로 갈라 눈에 보이게 둔다.
   새로고침하면 무엇이 사라지는지가 코드 구조에서 바로 읽혀야 한다.
2. **API 계층은 게임 규칙을 모른다.** `api/` 는 HTTP 와 오류 모양만 안다. 펀더멘털·v2 필드가
   붙을 때 넓어지는 곳이 `api/types.ts` 하나가 되게 하는 장치다.
3. **돈 계산은 서버의 내림을 그대로 복제한다.** 어긋나면 `insufficient_cash` 로 드러난다.
   여기가 단위 테스트 1순위다.
4. **폴링 루프는 죽지 않는다.** 네트워크 실패·분석 대기·잠금 중에도 계속 돈다.
   분석이 몇 초 걸리는 동안 시장이 움직이는 것이 게임의 비용이므로, 그 시간을 화면이 보여줘야 한다.
5. **화면은 정답을 추측하지 않는다.** 미분석 기사에 방향을 암시하는 색·아이콘·정렬을 쓰지 않는다.
   헤드라인 톤으로 색을 칠하는 순간 낚시 뉴스가 무력해진다. `impact`·`kind` 를 유추하는 코드는
   어떤 형태로도 두지 않는다.

## 3. 기술 스택

메이저 라인만 고정하고 정확한 버전은 설치 시점 최신 안정판을 락파일에 박는다.

| | 무엇 | 비고 |
|---|---|---|
| 런타임 | Node 22.17.1 | 이미 설치돼 있음 |
| 빌드 | Vite | `npm create vite@latest frontend -- --template react-ts` 로 시작 |
| UI | React 19 계열 | |
| 언어 | TypeScript, `strict: true` | `noUncheckedIndexedAccess` 도 켠다 |
| 상태 | `zustand` 5 계열 | 2KB. 셀렉터 구독 |
| 테스트 | `vitest` + `@testing-library/react` + `@testing-library/user-event` | |
| 모의 서버 | `msw` 2 계열 | `api.md` 의 캡처 JSON 을 픽스처로 그대로 쓴다 |
| 린트·포맷 | ESLint flat config + Prettier | 템플릿이 flat config 를 이미 준다 |

새 의존성은 이게 전부다. 차트·날짜·UI 킷은 넣지 않는다.

## 4. 프로젝트 구조

```
frontend/
  index.html
  vite.config.ts
  tsconfig.json
  package.json
  src/
    main.tsx
    App.tsx
    api/
      types.ts          api.md §4 스냅샷·stocks[]·news[] 와 액션 응답 타입
      client.ts         fetch 래퍼. 오류를 ApiError 하나로 정규화
      endpoints.ts      6개 함수. 게임 규칙 없음
    store/
      gameStore.ts      서버 스냅샷 그대로
      derivedStore.ts   새로고침하면 사라지는 것 — 이력·평단·누적 뉴스
      merge.ts          순수 병합 함수 (테스트 대상)
    hooks/
      useGameLoop.ts    500ms 폴링, since 커서, 문서 가시성, 시퀀스 가드
    lib/
      money.ts          수수료·내림·최대 매수 수량 (테스트 대상)
      derive.ts         tick 기준 age·ramp 파생 (테스트 대상)
    components/
      account/  chart/  news/  order/  watchlist/  system/
    mocks/
      handlers.ts       MSW. api.md 캡처 JSON
```

`store/` 는 `fetch` 를 모르고, `api/` 는 스토어를 모른다. `lib/` 는 둘 다 모르는 순수 함수다.

## 5. API 계층

### 오류 정규화

모든 오류를 `ApiError { status, code, message }` 하나로 좁힌다.

| 응답 | 정규화 |
|---|---|
| `{ detail: { code, message } }` | 그대로 매핑. `message` 는 한국어라 사용자에게 그대로 노출 |
| `422` (detail 이 **배열**) | `code: "bad_request"`, `message: "요청 형식이 올바르지 않습니다."` |
| 네트워크 실패 | `status: 0`, `code: "network"` |
| 그 외 5xx | `code: "server"` |

`422` 와 거대 `qty` 로 인한 원시 `500`(`api.md` §7-1, §7-2)은 **입력 단계에서 막는다** —
수량은 정수 스테퍼이고 상한은 매수 시 최대 매수 수량, 매도 시 `held` 다.

### 엔드포인트

| 함수 | 호출 | 반환 |
|---|---|---|
| `newGame()` | `POST /api/game` | 스냅샷 |
| `getState(sid, since)` | `GET /api/state` | 스냅샷 |
| `trade(sid, symbol, side, qty)` | `POST /api/trade` | 체결 결과 |
| `analyze(sid, newsId)` | `POST /api/analyze` | 분석 결과 |
| `grind(sid)` | `POST /api/grind` | `{ payout, lock_remaining, grind_count }` |
| `nextRound(sid)` | `POST /api/next-round` | 스냅샷 |

## 6. 상태 구조

### `gameStore` — 서버가 준 것

스냅샷 필드를 **그대로** 담는다. 가공하지 않는다. `bankrupt`·`goal_reached` 같은
판정도 서버 값을 쓰고 다시 계산하지 않는다.

### `derivedStore` — 내가 쌓은 것

| 항목 | 어떻게 |
|---|---|
| 가격 이력 | 종목별 최근 **60틱**. `tick` 이 바뀔 때만 append (500ms 폴링이라 같은 tick 이 두 번 온다) |
| 누적 뉴스 | `news_id` 기준 **upsert**. `since` 로 새 것만 받으므로 목록은 여기서만 자란다 |
| 평단·실현손익 | 체결 응답으로만 갱신 |
| 분석 결과 | `analyze` 응답을 해당 뉴스에 병합 |

### 파생이 필요한 두 값 — `since` 의 대가

`since` 를 쓰면 이미 받은 기사는 다시 오지 않는다. 그래서 **서버가 준 상대 시간이 화면에서 얼어붙는다.**
받은 순간의 `tick` 으로 절대 시각을 만들어 두고 매 프레임 다시 계산한다.

```
수신 시:  publish_tick  = snapshot.tick - news.age_seconds
표시 시:  age           = current_tick - publish_tick

분석 시:  ramp_end_tick = current_tick + resp.ramp_remaining
표시 시:  remaining     = max(0, ramp_end_tick - current_tick)
```

`analyze` 응답에는 `tick` 이 없으므로 수신 직후의 최신 스냅샷 `tick` 을 기준점으로 쓴다.
오차는 최대 한 폴링 간격(500ms)이고 램프는 수십 초 단위라 무시할 수 있다.

`ramp_remaining` 이 `0` 이면 `ramp_end_tick` 을 만들지 않는다. 그 기사는 **끝난 기회**이고,
`current_tick` 까지 밴드를 칠하면 아직 진행 중인 것처럼 보인다.

**대안(매번 `since=-1` 로 전량 수신)을 택하지 않은 이유** — 라운드가 쌓이면 `news_total` 이
계속 자라고, 해설 문장까지 500ms 마다 다시 받게 된다. 얼어붙는 값 두 개는 위 두 줄로 해결된다.

### 병합 규칙

1. **액션 응답이 이긴다.** `trade`·`analyze` 응답의 `cash`/`equity`/`analyses_left` 는 즉시 반영한다.
   다음 폴링 스냅샷이 권위를 되찾으므로 어긋나도 500ms 안에 수렴한다.
2. **폴링 응답은 시퀀스 번호로 거른다.** 요청마다 번호를 달고, 더 낮은 번호의 응답은 버린다.
   순서가 뒤바뀐 응답이 새 상태를 덮는 것을 막는다.
3. **폴링은 하나만 떠 있는다.** 앞선 요청이 안 끝났으면 새로 쏘지 않는다.
4. **노가다 보수는 반영하지 않는다.** `payout` 은 표시용이다. 실제 현금은 잠금이 끝난 뒤
   폴링 스냅샷의 `cash` 로 들어온다.
5. **`held` 는 있는데 평단이 없으면 손익을 `—` 로 둔다.** 새로고침 후 상태다.
   모르는 값을 0 으로 채워 틀린 손익을 그리지 않는다.

## 7. 돈 계산 — `lib/money.ts`

서버와 어긋나면 안 되는 순수 함수들이다.

```
fee(price, qty)      = floor(price * qty * 0.002)
buyCost(price, qty)  = price * qty + fee(price, qty)
sellNet(price, qty)  = price * qty - fee(price, qty)
```

**최대 매수 수량** — 닫힌 식이 내림 때문에 정확하지 않으므로 근사 후 보정한다.

```
q = floor(cash / (price * 1.002))
while buyCost(price, q + 1) <= cash:  q += 1
while q > 0 and buyCost(price, q) > cash:  q -= 1
```

**평단** — 매수 시 수수료를 포함한 취득원가 기준, 내림.

```
매수: avg = floor((avg * held + buyCost(price, qty)) / (held + qty))
매도: avg 유지, 수량만 감소. 전량 매도 시 avg = 0
      실현손익 += sellNet(price, qty) - avg * qty
평가손익 = (현재가 - avg) * held
```

## 8. 기능 명세

11개다. 각 항목의 **판정 기준**이 그대로 테스트가 된다.

### F1 · 게임 시작과 세션 소멸

- 진입 시 `POST /api/game`. `session_id` 를 `sessionStorage` 에 저장해 새로고침 후 이어간다.
- 저장된 세션으로 `getState` 가 `404 no_session` 이면 — 서버 재시작이다 — 전용 화면을 띄우고
  `새 게임` 버튼만 준다. 조용히 새 게임을 시작하지 않는다.
- **시작 직후 `news` 는 빈 배열이 정상이다**(`api.md` §3). 빈 피드를 오류로 다루지 않고
  "첫 기사를 기다리는 중" 을 보여준다.

### F2 · 시장 폴링

- 500ms 간격. `since` 는 지금까지 받은 최대 `news_id`, 아직 하나도 없으면 `-1`.
- `document.hidden` 이면 멈추고, 복귀 시 즉시 1회 부른다. 그 사이 뜬 뉴스는 램프가 이미
  끝나 있고, 그것이 의도된 동작이다(`api.md` §1).
- **분석 대기 중에도 멈추지 않는다.** 기다리는 시간이 분석의 실질 비용이다.

### F3 · 종목 차트

- 선택된 종목의 최근 60틱을 SVG 라인으로. 데이터가 60틱보다 적으면 있는 만큼 그린다.
- **뉴스 마커** — 미분석 기사는 `publish_tick` 위치에 **점선 세로선만**. 방향을 암시하는
  색을 쓰지 않는다(원칙 5).
- **램프 밴드** — 분석한 기사만 `publish_tick ~ ramp_end_tick` 구간을 음영으로 칠한다.
  색은 `strength` 를 따르고, `none`(무영향)은 **중립색**이다 — 방향이 없기 때문이다.
  `already_priced_in` 이면 칠할 구간이 없으므로 밴드 대신 마커에 **`이미 반영됨`** 을 붙인다.
  분석은 판정만이 아니라 **기회의 남은 창**을 사는 것이라는 `api.md` §6 의 설계를
  화면으로 드러내는 부분이다.
- 이력은 새로고침하면 사라진다. 빈 차트에 "이력을 쌓는 중" 을 표시한다.

### F4 · 워치리스트

- 6종목: 이름·섹터·현재가·`change_pct`(**시작가 대비**)·`held`.
- 행 클릭으로 차트/주문 대상 전환.

### F5 · 주문

- 매수/매도 토글, 정수 스테퍼, `최대` 버튼.
- 상한: 매수는 §7 의 최대 매수 수량, 매도는 `held`. 이 상한이 `422`·거대 `qty` `500` 을 막는다.
- 확정 전에 **예상** 체결금액과 수수료를 보여주되 "체결가는 서버가 정합니다" 를 명시한다.
- 체결 후 화면은 **응답의 `price`/`fee`/`cash` 로만** 갱신한다. 낙관적 UI 금지.
- 실제 체결가가 주문 시 표시가와 다르면 그 차이를 체결 알림에 함께 보여준다.

### F6 · 계좌와 포트폴리오

- 현금 / 총자산 / 목표 / 진행바.
  `진행률 = (equity - round_start_equity) / (target - round_start_equity)`, 0~1 로 clamp.
- 보유 종목별 수량·평단·평가손익. 평단이 없으면 `—`(§6 병합 규칙 5).

### F7 · 뉴스 피드

- 최신순. 헤드라인·본문·종목·경과 시간(파생값)·`offline` 배지.
- 분석한 기사는 `label`·`commentary`·남은 램프 초를 함께 보여준다.
- 미분석 기사에는 판정 자리를 비워 둔다. 추측하지 않는다.

### F8 · AI 분석

- 기사마다 `분석` 버튼. `analyses_left` 를 항상 노출하고 0 이면 비활성.
- 호출 중 해당 기사에 로딩 상태. **그동안 시장은 계속 움직이고 화면도 계속 움직인다.**
- 응답의 `strength`/`label`/`commentary`/`ramp_remaining`/`offline` 을 병합하고
  `analyses_left` 를 즉시 반영한다.
- `400 no_analyses_left`·`404 no_news` 는 메시지를 그대로 노출한다.

### F9 · 파산과 노가다

- `bankrupt: true` 면 `노가다` 버튼이 열린다. **다른 UI 는 잠그지 않는다** —
  파산 상태에서도 매매와 분석은 계속 가능하다(`api.md` §3).
- 실행하면 `lock_remaining` 카운트다운. 잠금 중 매매·분석 버튼 비활성.
- **보수는 즉시 더하지 않는다.** `payout` 은 "잠금이 끝나면 들어옵니다" 로 안내하고,
  실제 증가는 폴링의 `cash` 로 확인한다.
- `grind_count` 를 보여준다. 보수가 3/5 로 줄어드는 것이 다음 판단의 재료다.

### F10 · 라운드 전환

- `goal_reached: true` 면 `다음 라운드` 버튼이 열린다.
- 성공 시 `round_no` 상승, `analyses_left` 5 리필, 새 `target`.
- **가격 이력과 평단은 유지한다.** 라운드 전환은 가격을 건드리지 않는다.
- `400 goal_not_reached` 는 정상 경로에서 발생하지 않지만 메시지를 노출한다.

### F11 · 연결 상태와 오류 표면

- 네트워크 실패 시 상단 배너 "연결 끊김 — 재시도 중". 폴링은 계속 돈다(원칙 4).
- 재연결되면 배너를 걷는다.
- 액션 오류(400·423)는 토스트로 `message` 를 그대로. 서버 문장이 이미 한국어다.
- `423 locked` 는 토스트보다 잠금 카운트다운이 이미 설명하므로 조용히 처리한다.

## 9. 개발 환경

### `vite.config.ts`

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:7999' } },
  },
  build: { outDir: '../backend/static', emptyOutDir: true },
})
```

프록시가 있으므로 프론트 코드의 모든 요청은 **상대 경로 `/api/...`** 다. 절대 URL 도
환경변수도 쓰지 않는다. 그래서 개발(프록시)과 배포(같은 오리진 정적 마운트)가
**같은 코드로 동작한다.**

### 스크립트

| | 하는 일 |
|---|---|
| `npm run dev` | Vite 5173. 백엔드는 `backend/run.sh` 로 따로 띄운다 |
| `npm run build` | `backend/static/` 에 산출. 이후 `run.sh` 만으로 `localhost:7999` 에서 게임 전체가 뜬다 |
| `npm test` | Vitest 1회 |
| `npm run test:watch` | 감시 모드 |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` / `format` | ESLint / Prettier |

### 두 서버를 띄우는 순서

```bash
cd backend && ./run.sh          # 7999 — 포트를 빠뜨리면 8000 으로 뜬다
cd frontend && npm run dev      # 5173 — /api 는 7999 로 프록시된다
```

### `.gitignore` 추가

```
frontend/node_modules/
backend/static/
```

`backend/static/` 은 빌드 산출물이므로 기존 "생성물 — 원본에서 다시 만들 수 있다" 절에 넣는다.

## 10. 테스트 전략

**네트워크도 실제 백엔드도 부르지 않는다.** 백엔드 122개가 지키는 성질을 그대로 가져간다.
MSW 핸들러의 응답 본문은 `api.md` 에 캡처된 실제 JSON 을 그대로 쓴다 — 문서가 곧 픽스처다.

| | 무엇 | 어디 |
|---|---|---|
| 1 | 수수료가 서버와 같이 내림된다 | `money.test.ts` |
| 2 | 최대 매수 수량이 경계에서 정확하다 (`buyCost(q) <= cash < buyCost(q+1)`) | `money.test.ts` |
| 3 | 평단이 매수 수수료를 포함해 내림된다 | `money.test.ts` |
| 4 | 전량 매도 후 평단이 0 으로 리셋된다 | `money.test.ts` |
| 5 | `age` 와 `ramp_remaining` 이 tick 기준으로 파생된다 | `derive.test.ts` |
| 6 | 같은 tick 이 두 번 와도 이력이 한 번만 쌓인다 | `merge.test.ts` |
| 7 | 뉴스가 `news_id` 기준으로 upsert 된다 | `merge.test.ts` |
| 8 | 낮은 시퀀스 응답이 버려진다 | `merge.test.ts` |
| 9 | `held` 만 있고 평단이 없으면 손익이 `—` 다 | `merge.test.ts` |
| 10 | 노가다 `payout` 이 현금에 즉시 더해지지 **않는다** | `merge.test.ts` |
| 11 | 시작 직후 빈 뉴스 배열이 오류로 처리되지 않는다 | 컴포넌트 |
| 12 | `404 no_session` 이 전용 화면을 띄운다 | 컴포넌트 + MSW |
| 13 | 미분석 기사에 방향 색이 칠해지지 않는다 | 컴포넌트 |
| 14 | 체결 후 화면이 응답의 `price`/`fee`/`cash` 를 따른다 | 컴포넌트 + MSW |
| 15 | 네트워크 실패 후에도 폴링이 계속된다 | `useGameLoop` + MSW |
| 16 | 분석 대기 중에도 폴링이 멈추지 않는다 | `useGameLoop` + MSW |

13번이 원칙 5의 방어선이다. 백엔드의 "스냅샷에 `impact` 가 없다" 테스트와 짝이 되는,
프론트 쪽의 정답 누출 방지다.

**테스트하지 않는 것** — SVG 픽셀 좌표, 애니메이션 타이밍, 미학. 미학은 아직 미선택이다.

## 11. 만들어야 하는 것

| 경로 | 무엇 | 신규 |
|---|---|---|
| `frontend/` 일체 | Vite 스캐폴드, 설정, 스크립트 | ● |
| `src/api/*` | 타입·클라이언트·엔드포인트 6개 | ● |
| `src/lib/money.ts` `derive.ts` | 순수 계산 | ● |
| `src/store/*` | 두 스토어 + 병합 함수 | ● |
| `src/hooks/useGameLoop.ts` | 폴링 | ● |
| `src/components/*` | F3~F11 화면 | ● |
| `src/mocks/handlers.ts` | MSW | ● |
| `.gitignore` | 두 줄 추가 | |

**백엔드는 한 줄도 건드리지 않는다.** 프록시가 CORS 를 대신하고 정적 마운트는 이미 있다.

## 12. 결정하지 않은 것

1. **미학 방향** — `design/` A·B·C 중 미선택. 이 문서 다음 라운드의 주제다.
2. **가격 이력과 평단을 서버가 줄 것인가** — `api.md` §7-4 의 열린 질문. 지금은 프론트가 들고
   있고 새로고침하면 사라진다. v2 를 손댈 때 함께 결정하는 것이 낫다.
3. **폴링 간격 500ms** — 권장값이다. 서버 계산이 간격에 무관하므로 부하를 보고 조정할 수 있다.
4. **이력 60틱** — 차트 가로폭과 램프 길이를 보고 조정한다. 램프가 60초보다 길면 밴드가
   화면 밖으로 나간다.
5. **`sessionStorage` 로 세션을 이어갈 것인가** — 이어가면 새로고침 후에도 판이 계속되지만,
   이력과 평단이 없는 반쪽 상태가 된다. F1 은 이어가는 쪽으로 잡았고 §6 규칙 5 가 그 반쪽
   상태를 정직하게 표시한다.
