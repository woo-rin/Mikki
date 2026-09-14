import { type ReactNode, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { getState, newGame } from '../../api/endpoints'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'

export const SESSION_KEY = 'mikki.session'

/**
 * 세션을 확보한 뒤에만 보드를 렌더한다.
 * 저장된 세션이 죽었으면 조용히 새 게임을 시작하지 않는다 — 판이 사라졌다는 사실을 알린다.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const sessionId = useGameStore((s) => s.sessionId)
  const sessionGone = useGameStore((s) => s.sessionGone)
  const [failed, setFailed] = useState<string | null>(null)
  const booted = useRef(false)

  async function start(): Promise<void> {
    setFailed(null)
    try {
      const snap = await newGame()
      sessionStorage.setItem(SESSION_KEY, snap.session_id)
      useGameStore.getState().reset()
      useDerivedStore.getState().reset()
      useGameStore.getState().setSession(snap.session_id)
      useGameStore.getState().applySnapshot(snap, 0)
      useDerivedStore.getState().record(snap)
    } catch (err) {
      setFailed(err instanceof ApiError ? err.message : '알 수 없는 오류입니다.')
    }
  }

  async function boot(): Promise<void> {
    setFailed(null)
    const saved = sessionStorage.getItem(SESSION_KEY)
    if (saved) {
      try {
        const snap = await getState(saved, -1)
        useGameStore.getState().setSession(saved)
        useGameStore.getState().applySnapshot(snap, 0)
        useDerivedStore.getState().record(snap)
      } catch (err) {
        if (err instanceof ApiError && err.code === 'no_session') {
          useGameStore.getState().setSessionGone(true)
        } else {
          setFailed(err instanceof ApiError ? err.message : '알 수 없는 오류입니다.')
        }
      }
      return
    }
    await start()
  }

  useEffect(() => {
    if (booted.current) return
    booted.current = true
    void boot()
  }, [])

  if (sessionGone) {
    return (
      <div className="gate">
        <h1>판이 사라졌습니다</h1>
        <p>서버가 다시 시작되어 이전 게임을 이어갈 수 없습니다.</p>
        <button type="button" onClick={() => void start()}>새 게임</button>
      </div>
    )
  }

  if (failed !== null) {
    return (
      <div className="gate">
        <h1>시작하지 못했습니다</h1>
        <p role="alert">{failed}</p>
        <p className="hint">백엔드가 7999 포트에 떠 있는지 확인하세요 — <code>backend/run.sh</code></p>
        <button type="button" onClick={() => void boot()}>다시 시도</button>
      </div>
    )
  }

  if (sessionId === null) {
    return <div className="gate"><p>게임을 준비하는 중…</p></div>
  }

  return <>{children}</>
}
