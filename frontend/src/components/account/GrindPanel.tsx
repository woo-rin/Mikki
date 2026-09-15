import { useState } from 'react'
import { ApiError } from '../../api/client'
import { grind } from '../../api/endpoints'
import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

export function GrindPanel() {
  const snap = useGameStore((s) => s.snapshot)
  const sessionId = useGameStore((s) => s.sessionId)
  const pushToast = useUiStore((s) => s.pushToast)
  const [busy, setBusy] = useState(false)

  // 평소에도 열려 있다. 파산은 더 이상 전제가 아니라 급함의 표시일 뿐이다.
  if (!snap || !sessionId) return null

  async function run(): Promise<void> {
    if (!sessionId) return
    setBusy(true)
    try {
      const res = await grind(sessionId)
      // 보수는 더하지 않는다 — 잠금이 끝난 뒤 폴링으로 들어온다.
      useGameStore.getState().applyGrind(res)
      pushToast(
        `노가다 ${res.grind_count}회차 · 보수 ${won(res.payout)} 은 잠금이 끝나면 들어옵니다.`,
        'info',
      )
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '노가다에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={snap.bankrupt ? 'panel warn' : 'panel'}>
      <h2>{snap.bankrupt ? '파산' : '노가다'}</h2>
      {snap.bankrupt && (
        <p>
          총자산이 10만원 아래로 떨어졌습니다. <strong>매매와 분석은 계속 가능합니다.</strong>
        </p>
      )}
      {snap.locked ? (
        <p className="num">{`잠금 ${snap.lock_remaining}초 남음 · ${snap.grind_count}회차`}</p>
      ) : (
        <>
          <button type="button" className="primary" disabled={busy} onClick={() => void run()}>
            노가다
          </button>
          <p className="hint">
            {`120초간 매매와 분석이 잠깁니다. 그동안에도 시장은 움직입니다. 보수는 회차마다 3/5 로 줄어듭니다${
              snap.grind_count > 0 ? ` — 지금까지 ${snap.grind_count}회차` : ''
            }.`}
          </p>
        </>
      )}
    </section>
  )
}
