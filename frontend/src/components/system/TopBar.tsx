import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'

/**
 * 항상 보이는 요약. 라운드 달성처럼 **놓치면 안 되는 것**은 탭에 묻지 않고 여기 띄운다.
 */
export function TopBar() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  return (
    <header className="topbar">
      <strong className="brand">미끼</strong>
      <span className="num">{`R${snap.round_no}`}</span>
      <span className="num">{`${snap.tick}s`}</span>

      <span className="spacer" />

      <span className="tb-item">
        <span className="tb-key">현금</span>
        <span className="num">{won(snap.cash)}</span>
      </span>
      <span className="tb-item">
        <span className="tb-key">총자산</span>
        <span className="num">{won(snap.equity)}</span>
      </span>
      <span className="tb-item">
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

      {snap.goal_reached && <span className="tb-goal">목표 달성 — 다음 라운드로</span>}
    </header>
  )
}
