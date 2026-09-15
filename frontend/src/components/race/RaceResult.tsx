import { useState } from 'react'
import { ApiError } from '../../api/client'
import { newGame } from '../../api/endpoints'
import { won } from '../../lib/format'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

/**
 * 경주가 끝나면 화면 전체를 덮는다. 서버의 status 로 켜지므로 새로고침해도 남는다.
 *
 * 승자를 순위가 아니라 **어떻게 이겼는지**로 설명한다. 조기 종료면 목표를 먼저
 * 확정한 사람이 1위라 현금이 2위보다 적을 수 있다 — 그 경우 순위표만 보면
 * 틀린 것처럼 보인다.
 */
export function RaceResult() {
  const snap = useGameStore((s) => s.snapshot)
  const pushToast = useUiStore((s) => s.pushToast)
  const [busy, setBusy] = useState(false)

  if (!snap || snap.status !== 'finished' || !snap.ranking) return null

  const ranking = snap.ranking
  const champion = ranking[0]
  const iWon = snap.winner === 'you'
  // 승자가 현금 1위가 아니면 조기 종료다 — 목표를 먼저 확정했다는 뜻이다.
  const byCash = champion !== undefined
    && ranking.every((r) => r.cash <= champion.cash)

  async function restart(): Promise<void> {
    setBusy(true)
    try {
      const fresh = await newGame()
      useDerivedStore.getState().reset()
      useGameStore.getState().setSession(fresh.session_id)
      useGameStore.getState().forceSnapshot(fresh)
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '새 판을 열지 못했습니다.')
      setBusy(false)
    }
  }

  return (
    <div className="race-over" role="dialog" aria-modal="true" aria-label="경주 결과">
      <div className="race-card">
        <p className="race-title">
          {iWon ? '당신이 이겼습니다' : `${champion?.name ?? '?'} 승`}
        </p>
        <p className="hint">{byCash ? '마감 · 현금 1위' : '목표에 먼저 도달'}</p>

        <table className="grid race-rank">
          <tbody>
            {ranking.map((row) => (
              <tr
                key={row.name}
                data-testid="rank-row"
                data-me={String(row.is_player)}
                className={row.is_player ? 'selected' : undefined}
              >
                <td className="num">{row.rank}</td>
                <td>{row.name}</td>
                <td className="num">{won(row.cash)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <button type="button" className="primary" disabled={busy} onClick={() => void restart()}>
          {busy ? '여는 중…' : '다시 하기'}
        </button>
      </div>
    </div>
  )
}
