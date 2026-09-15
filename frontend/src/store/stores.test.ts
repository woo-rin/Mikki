import { beforeEach, describe, expect, it } from 'vitest'
import {
  baseSnapshot, capturedAnalyze, capturedCompanyAnalysis, capturedTrade, sampleNews,
} from '../mocks/fixtures'
import { useDerivedStore } from './derivedStore'
import { useGameStore } from './gameStore'
import { useUiStore } from './uiStore'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
})

describe('gameStore', () => {
  it('더 새로운 스냅샷만 받는다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot({ tick: 10 }), 1)
    g.applySnapshot(baseSnapshot({ tick: 3 }), 0) // 뒤늦게 도착한 옛 응답
    expect(useGameStore.getState().snapshot?.tick).toBe(10)
  })

  it('체결 응답이 즉시 현금에 반영된다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot(), 1)
    g.applyTrade(capturedTrade)
    expect(useGameStore.getState().snapshot?.cash).toBe(910_586)
  })

  it('분석 응답이 즉시 잔여 횟수에 반영된다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot(), 1)
    g.applyAnalyze(capturedAnalyze)
    expect(useGameStore.getState().snapshot?.analyses_left).toBe(4)
  })

  it('노가다는 잠그지만 현금을 늘리지 않는다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot({ cash: 50_000 }), 1)
    g.applyGrind({ payout: 200_000, lock_remaining: 120, grind_count: 1 })
    const snap = useGameStore.getState().snapshot
    expect(snap?.cash).toBe(50_000)
    expect(snap?.locked).toBe(true)
  })

  it('기업분석 응답이 즉시 잔여 횟수에 반영된다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot(), 1)
    g.applyCompanyAnalysis(capturedCompanyAnalysis)
    expect(useGameStore.getState().snapshot?.company_analyses_left).toBe(1)
  })

  it('forceSnapshot 은 시퀀스를 건드리지 않아 이후 폴링이 계속 먹힌다', () => {
    const g = useGameStore.getState()
    g.applySnapshot(baseSnapshot({ tick: 1 }), 1)
    g.forceSnapshot(baseSnapshot({ round_no: 2, tick: 1 }))
    expect(useGameStore.getState().snapshot?.round_no).toBe(2)
    useGameStore.getState().applySnapshot(baseSnapshot({ tick: 99 }), 2)
    expect(useGameStore.getState().snapshot?.tick).toBe(99)
  })
})

describe('derivedStore', () => {
  it('스냅샷에서 뉴스를 쌓는다 — 가격 이력은 서버가 들고 있다', () => {
    const d = useDerivedStore.getState()
    d.record(baseSnapshot({ tick: 1, news: [sampleNews()] }))
    d.record(baseSnapshot({ tick: 2 }))
    expect(useDerivedStore.getState().feed).toHaveLength(1)
    // 가격 이력과 평단은 서버가 들고 있다 — 여기 없는 것이 맞다
    expect('history' in useDerivedStore.getState()).toBe(false)
    expect('positions' in useDerivedStore.getState()).toBe(false)
  })

  it('분석 결과가 피드에 붙는다', () => {
    const d = useDerivedStore.getState()
    d.record(baseSnapshot({ tick: 300, news: [sampleNews()] }))
    useDerivedStore.getState().recordAnalysis(capturedAnalyze, 300)
    expect(useDerivedStore.getState().feed[0]?.analysis?.label).toBe('무영향')
  })
})

describe('기업분석 보관', () => {
  it('종목별로 보관한다', () => {
    useDerivedStore.getState().record(baseSnapshot({ round_no: 1 }))
    useDerivedStore.getState().recordValuation(capturedCompanyAnalysis)
    expect(useDerivedStore.getState().valuations['geno']?.label).toBe('고평가')
    expect(useDerivedStore.getState().valuations['hanbit']).toBeUndefined()
  })

  it('같은 라운드에서는 유지된다', () => {
    useDerivedStore.getState().record(baseSnapshot({ round_no: 1, tick: 1 }))
    useDerivedStore.getState().recordValuation(capturedCompanyAnalysis)
    useDerivedStore.getState().record(baseSnapshot({ round_no: 1, tick: 2 }))
    expect(useDerivedStore.getState().valuations['geno']).toBeDefined()
  })

  it('라운드가 바뀌면 비운다 — 적정가가 분기마다 움직인다', () => {
    useDerivedStore.getState().record(baseSnapshot({ round_no: 1 }))
    useDerivedStore.getState().recordValuation(capturedCompanyAnalysis)
    useDerivedStore.getState().record(baseSnapshot({ round_no: 2 }))
    expect(useDerivedStore.getState().valuations).toEqual({})
  })
})

describe('uiStore', () => {
  it('토스트를 쌓고 지운다', () => {
    useUiStore.getState().pushToast('현금이 부족합니다.', 'error')
    const id = useUiStore.getState().toasts[0]?.id
    expect(id).toBeDefined()
    useUiStore.getState().dismissToast(id!)
    expect(useUiStore.getState().toasts).toHaveLength(0)
  })
})
