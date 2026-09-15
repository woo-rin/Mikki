import { useEffect, useRef } from 'react'
import { ApiError } from '../api/client'
import { getState } from '../api/endpoints'
import { useDerivedStore } from '../store/derivedStore'
import { useGameStore } from '../store/gameStore'
import { maxNewsId, maxTradeSeq } from '../store/merge'

interface Options {
  intervalMs?: number
}

/**
 * 시장을 굴리는 루프. 서버에 타이머가 없으므로 이 요청이 도착할 때 시간이 흐른다.
 *
 * - 요청은 항상 하나만 떠 있는다.
 * - 응답에 시퀀스 번호를 달아 순서가 뒤바뀐 응답을 버린다.
 * - 탭이 숨으면 멈추고, 돌아오면 즉시 한 번 부른다. 그 사이 뜬 뉴스의 램프가
 *   이미 끝나 있는 것은 의도된 동작이다 (api.md §1).
 * - 네트워크 실패로 죽지 않는다. 분석이 몇 초 걸려도 멈추지 않는다.
 */
export function useGameLoop({ intervalMs = 500 }: Options = {}): void {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inFlight = useRef(false)
  const seq = useRef(0)
  const stopped = useRef(false)

  useEffect(() => {
    stopped.current = false

    const poll = async (): Promise<void> => {
      const { sessionId, sessionGone } = useGameStore.getState()
      if (stopped.current || sessionGone || !sessionId) return
      if (inFlight.current || document.hidden) return

      inFlight.current = true
      const mySeq = ++seq.current
      try {
        const derived = useDerivedStore.getState()
        const since = maxNewsId(derived.feed)
        const snap = await getState(sessionId, since, maxTradeSeq(derived.trades))
        if (stopped.current) return
        useGameStore.getState().setConnected(true)
        useGameStore.getState().applySnapshot(snap, mySeq)
        useDerivedStore.getState().record(snap)
      } catch (err) {
        if (stopped.current) return
        if (err instanceof ApiError && err.code === 'no_session') {
          useGameStore.getState().setSessionGone(true)
          return
        }
        // 네트워크 실패는 배너로 알리되 루프는 계속 돈다.
        useGameStore.getState().setConnected(!(err instanceof ApiError && err.code === 'network'))
      } finally {
        inFlight.current = false
      }
    }

    const tick = (): void => {
      void poll().finally(() => {
        if (stopped.current || useGameStore.getState().sessionGone) return
        timer.current = setTimeout(tick, intervalMs)
      })
    }

    const onVisible = (): void => {
      if (!document.hidden) void poll()
    }

    tick()
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      stopped.current = true
      if (timer.current !== null) clearTimeout(timer.current)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [intervalMs])
}
