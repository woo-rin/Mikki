import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, sampleNews } from '../../mocks/fixtures'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { RoundPanel } from './RoundPanel'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useGameStore.getState().setSession('s')
})

describe('라운드 전환', () => {
  it('목표 미달이면 버튼이 없다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ goal_reached: false }), 1)
    const { container } = render(<RoundPanel />)
    expect(container).toBeEmptyDOMElement()
  })

  it('목표에 닿으면 다음 라운드로 가고 분석이 리필된다', async () => {
    useGameStore.getState().applySnapshot(
      baseSnapshot({ goal_reached: true, equity: 3_000_000, analyses_left: 0 }),
      1,
    )
    render(<RoundPanel />)
    await userEvent.click(screen.getByRole('button', { name: '다음 라운드' }))

    // 전환되면 goal_reached 가 내려가 패널 자체가 사라진다. 스토어로 단정한다.
    await waitFor(() => expect(useGameStore.getState().snapshot?.round_no).toBe(2))
    expect(useGameStore.getState().snapshot?.analyses_left).toBe(5)
  })

  it('시퀀스를 망가뜨리지 않는다 — 이후 폴링이 계속 먹힌다', async () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ goal_reached: true }), 1)
    render(<RoundPanel />)
    await userEvent.click(screen.getByRole('button', { name: '다음 라운드' }))
    await waitFor(() => expect(useGameStore.getState().snapshot?.round_no).toBe(2))

    useGameStore.getState().applySnapshot(baseSnapshot({ round_no: 2, tick: 99 }), 2)
    expect(useGameStore.getState().snapshot?.tick).toBe(99)
  })

  it('라운드가 바뀌어도 뉴스 피드는 남는다', async () => {
    const snap = baseSnapshot({ goal_reached: true, tick: 7, news: [sampleNews()] })
    useGameStore.getState().applySnapshot(snap, 1)
    useDerivedStore.getState().record(snap)
    render(<RoundPanel />)
    await userEvent.click(screen.getByRole('button', { name: '다음 라운드' }))
    await waitFor(() => expect(useGameStore.getState().snapshot?.round_no).toBe(2))

    expect(useDerivedStore.getState().feed).toHaveLength(1)
  })
})
