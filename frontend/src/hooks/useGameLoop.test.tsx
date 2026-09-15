import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, sampleNews } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { useDerivedStore } from '../store/derivedStore'
import { useGameStore } from '../store/gameStore'
import { useGameLoop } from './useGameLoop'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useGameStore.getState().setSession('s')
})

describe('폴링 루프', () => {
  it('세션이 있으면 반복해서 폴링한다', async () => {
    let calls = 0
    server.use(
      http.get('/api/state', () => {
        calls += 1
        return HttpResponse.json(baseSnapshot({ tick: calls }))
      }),
    )
    renderHook(() => useGameLoop({ intervalMs: 10 }))
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(3))
  })

  it('받은 최대 news_id 를 since 로 보낸다', async () => {
    const seen: string[] = []
    server.use(
      http.get('/api/state', ({ request }) => {
        const since = new URL(request.url).searchParams.get('since') ?? ''
        seen.push(since)
        return HttpResponse.json(
          baseSnapshot({
            tick: seen.length,
            news: seen.length === 1 ? [sampleNews({ news_id: 4 })] : [],
          }),
        )
      }),
    )
    renderHook(() => useGameLoop({ intervalMs: 10 }))
    await waitFor(() => expect(seen.length).toBeGreaterThanOrEqual(3))
    expect(seen[0]).toBe('-1')
    expect(seen[seen.length - 1]).toBe('4')
  })

  it('네트워크가 끊겨도 루프가 계속 돌고, 복구되면 배너가 걷힌다', async () => {
    let calls = 0
    server.use(
      http.get('/api/state', () => {
        calls += 1
        if (calls <= 2) return HttpResponse.error()
        return HttpResponse.json(baseSnapshot({ tick: calls }))
      }),
    )
    // 끊긴 구간이 waitFor 의 폴링 사이로 지나갈 수 있어 전이를 구독으로 기록한다
    const seen: boolean[] = []
    const unsub = useGameStore.subscribe((s) => seen.push(s.connected))

    renderHook(() => useGameLoop({ intervalMs: 10 }))
    await waitFor(() => expect(calls).toBeGreaterThan(3))
    unsub()

    expect(seen).toContain(false) // 끊긴 것을 알렸다
    expect(useGameStore.getState().connected).toBe(true) // 복구되면 걷힌다
  })

  it('세션이 사라지면 멈추고 전용 상태를 세운다', async () => {
    server.use(
      http.get('/api/state', () =>
        HttpResponse.json(
          { detail: { code: 'no_session', message: '세션을 찾을 수 없습니다.' } },
          { status: 404 },
        ),
      ),
    )
    renderHook(() => useGameLoop({ intervalMs: 10 }))
    await waitFor(() => expect(useGameStore.getState().sessionGone).toBe(true))
  })

  it('느린 분석이 떠 있어도 폴링이 멈추지 않는다', async () => {
    let polls = 0
    server.use(
      http.get('/api/state', () => {
        polls += 1
        return HttpResponse.json(baseSnapshot({ tick: polls }))
      }),
      http.post('/api/analyze', () => new Promise<Response>(() => {})),
    )
    renderHook(() => useGameLoop({ intervalMs: 10 }))
    void fetch('/api/analyze', { method: 'POST', body: '{}' }).catch(() => {})
    await waitFor(() => expect(polls).toBeGreaterThanOrEqual(4))
  })
})
