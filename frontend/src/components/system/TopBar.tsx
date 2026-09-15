import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'

/**
 * 항상 보이는 요약. 라운드 달성처럼 **놓치면 안 되는 것**은 탭에 묻지 않고 여기 띄운다.
 */
/** 남은 시간을 분:초로. 경주에는 결승선이 있다. */
function clock(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return `${m}:${String(seconds - m * 60).padStart(2, '0')}`
}

export function TopBar() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  return (
    <header className="topbar">
      <strong className="brand">미끼</strong>
      <span
        className={snap.seconds_left <= 60 ? 'num clock urgent' : 'num clock'}
        aria-label="남은 시간"
      >
        {clock(snap.seconds_left)}
      </span>

      <span className="spacer" />

      <span className="tb-item" aria-label="현금">
        <span className="tb-key">현금</span>
        <span className="num">{won(snap.cash)}</span>
      </span>
      <span className="tb-item" aria-label="총자산">
        <span className="tb-key">총자산</span>
        <span className="num">{won(snap.equity)}</span>
      </span>
      <span className="tb-item" aria-label="목표 자산">
        <span className="tb-key">목표</span>
        <span className="num">{won(snap.target)}</span>
      </span>

      <span className="tb-item" aria-label="남은 AI 분석">
        <span className="tb-key">분석</span>
        <span className="num">{snap.analyses_left}</span>
      </span>
      <span className="tb-item" aria-label="남은 기업분석">
        <span className="tb-key">기업</span>
        <span className="num">{snap.company_analyses_left}</span>
      </span>

      {snap.goal_reached && <span className="tb-goal">목표 달성</span>}
    </header>
  )
}
