import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'

export function AccountPanel() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  const span = snap.target - snap.round_start_equity
  const progress =
    span <= 0
      ? 100
      : Math.round(
          Math.min(1, Math.max(0, (snap.equity - snap.round_start_equity) / span)) * 100,
        )

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
