import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, capturedAnalyze, sampleNews } from '../../mocks/fixtures'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { PriceChart } from './PriceChart'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useUiStore.getState().select('pixel')
})

/** 서버가 history 를 들고 있다. n틱이 지난 상태의 스냅샷 하나를 만든다. */
function feedTicks(n: number) {
  const prices = Array.from({ length: n }, (_, t) => 33_000 + t * 100)
  const tick = n - 1
  const snap = baseSnapshot({
    tick,
    // publishTick = tick - age_seconds = 1
    news: [sampleNews({ symbol: 'pixel', age_seconds: tick - 1 })],
    stocks: baseSnapshot().stocks.map((s) =>
      s.symbol === 'pixel'
        ? { ...s, price: prices[n - 1] ?? 33_000, history: prices }
        : s,
    ),
  })
  useGameStore.getState().applySnapshot(snap, 1)
  useDerivedStore.getState().record(snap)
}

describe('가격 차트', () => {
  it('첫 tick 전에는 그릴 것이 없다고 말한다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<PriceChart />)
    expect(screen.getByText('이력을 쌓는 중…')).toBeInTheDocument()
  })

  it('이력이 쌓이면 선을 그린다', () => {
    feedTicks(5)
    const { container } = render(<PriceChart />)
    const line = container.querySelector('polyline')
    expect(line).not.toBeNull()
    expect(line?.getAttribute('points')?.split(' ')).toHaveLength(5)
  })

  it('미분석 기사는 점선 마커만 남긴다 — 방향 색이 없다', () => {
    feedTicks(5)
    const { container } = render(<PriceChart />)
    const marker = container.querySelector('[data-testid="marker-0"]')
    expect(marker).not.toBeNull()
    expect(marker?.getAttribute('stroke-dasharray')).toBeTruthy()
    expect(container.querySelector('[data-testid="band-0"]')).toBeNull()
  })

  it('분석한 기사만 램프 밴드를 얻는다', () => {
    feedTicks(5)
    useDerivedStore.getState().recordAnalysis(
      { ...capturedAnalyze, strength: 'up_strong', ramp_remaining: 3, already_priced_in: false },
      4,
    )
    const { container } = render(<PriceChart />)
    expect(container.querySelector('[data-testid="band-0"]')).not.toBeNull()
  })

  it('이미 반영된 기사에는 밴드를 그리지 않는다', () => {
    feedTicks(5)
    useDerivedStore.getState().recordAnalysis(capturedAnalyze, 4) // ramp_remaining 0
    const { container } = render(<PriceChart />)
    expect(container.querySelector('[data-testid="band-0"]')).toBeNull()
  })
})
