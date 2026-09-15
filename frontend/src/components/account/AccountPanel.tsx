import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'

export function AccountPanel() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  // 진행은 **현금**으로 잰다. 사서 오르기만 하면 안 움직이는 것이 맞다 —
  // 목표는 "레이스를 얼마나 달렸나" 이고 팔아서 확정한 것만 센다.
  const progress =
    snap.target <= 0
      ? 100
      : Math.round(Math.min(1, Math.max(0, snap.cash / snap.target)) * 100)

  return (
    <section className="panel">
      <h2>계좌</h2>
      <dl className="kv">
        <dt>현금</dt><dd className="num">{won(snap.cash)}</dd>
        <dt>총자산</dt><dd className="num">{won(snap.equity)}</dd>
        <dt>목표</dt><dd className="num">{won(snap.target)}</dd>
        <dt>AI 분석</dt><dd className="num">{`${snap.analyses_left} / 5`}</dd>
      </dl>
      <div
        className="progress"
        role="progressbar"
        aria-label="목표 진행률"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
    </section>
  )
}
