import { useGameStore } from '../../store/gameStore'

/**
 * 곡괭이를 휘두르는 픽토그램. 인라인 SVG 라 외부 요청이 없다.
 *
 * 팔과 도구만 원점을 어깨에 두고 회전한다. 몸통은 고정이라 스윙이 사람처럼 보인다.
 */
function Worker() {
  return (
    <svg className="worker" viewBox="0 0 120 100" role="img" aria-hidden="true">
      {/* 바닥 */}
      <line x1="10" y1="88" x2="110" y2="88" className="worker-ground" />
      {/* 머리 */}
      <circle cx="46" cy="24" r="9" className="worker-ink" />
      {/* 몸통 */}
      <line x1="46" y1="33" x2="46" y2="62" className="worker-ink" />
      {/* 다리 */}
      <line x1="46" y1="62" x2="34" y2="88" className="worker-ink" />
      <line x1="46" y1="62" x2="60" y2="88" className="worker-ink" />
      {/* 팔 + 곡괭이 — 어깨(46,40)를 축으로 함께 돈다 */}
      <g className="worker-swing">
        <line x1="46" y1="40" x2="78" y2="30" className="worker-ink" />
        <line x1="78" y1="30" x2="96" y2="16" className="worker-tool" />
        <path d="M88 10 Q98 12 100 22" className="worker-tool" fill="none" />
      </g>
      {/* 튀는 흙 — 내리칠 때만 보인다 */}
      <g className="worker-dust">
        <circle cx="92" cy="84" r="2" />
        <circle cx="100" cy="80" r="1.5" />
        <circle cx="84" cy="80" r="1.5" />
      </g>
    </svg>
  )
}

/**
 * 잠금 중 화면 전체를 덮는다. **조작을 완전히 막는다** — 노가다는 자리를 비우는
 * 것이고, 돌아와 보니 시장이 변해 있는 것이 이 기능의 값이다.
 *
 * 블러 너머로 차트와 티커가 계속 움직이는 것이 보인다. 만질 수는 없고 보이기만
 * 한다 — "그동안에도 시장은 움직입니다" 를 문장이 아니라 그림으로 보여준다.
 *
 * 남은 초는 서버의 lock_remaining 을 그대로 쓴다. 클라이언트 타이머를 돌리면
 * 새로고침에 사라지고 서버와 어긋난다.
 */
export function GrindOverlay() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap || !snap.locked) return null

  return (
    <div
      className="grind-overlay"
      data-testid="grind-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="노가다 중"
    >
      <div className="grind-card">
        <Worker />
        <p className="grind-title">노가다 중</p>
        <p className="grind-count" role="timer" aria-live="polite">
          <span className="grind-seconds num">{snap.lock_remaining}</span>
          <span className="grind-unit">초</span>
        </p>
        <p className="hint">{`${snap.grind_count}회차 · 끝나면 보수가 현금으로 들어옵니다.`}</p>
        <p className="hint">그동안에도 시장은 계속 움직입니다.</p>
      </div>
    </div>
  )
}
