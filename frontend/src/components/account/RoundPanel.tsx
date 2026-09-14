import { useState } from 'react'
import { ApiError } from '../../api/client'
import { nextRound } from '../../api/endpoints'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

export function RoundPanel() {
  const snap = useGameStore((s) => s.snapshot)
  const sessionId = useGameStore((s) => s.sessionId)
  const pushToast = useUiStore((s) => s.pushToast)
  const [busy, setBusy] = useState(false)

  if (!snap || !snap.goal_reached || !sessionId) return null

  async function go(): Promise<void> {
    if (!sessionId) return
    setBusy(true)
    try {
      const next = await nextRound(sessionId)
      // 가격 이력과 평단은 건드리지 않는다. 라운드 전환은 가격을 바꾸지 않는다.
      useGameStore.getState().forceSnapshot(next)
      useDerivedStore.getState().record(next)
      pushToast(`${next.round_no}라운드 시작 · 분석 ${next.analyses_left}회 리필`, 'info')
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '라운드를 넘기지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel goal">
      <h2>목표 달성</h2>
      <button type="button" className="primary" disabled={busy} onClick={() => void go()}>
        다음 라운드
      </button>
    </section>
  )
}
