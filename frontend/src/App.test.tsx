import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Board } from './App'
import { baseSnapshot } from './mocks/fixtures'
import { useGameStore } from './store/gameStore'
import { useUiStore } from './store/uiStore'

// 폴링은 껍데기 테스트의 관심사가 아니다. 돌긴 하되 네트워크는 안 탄다.
vi.mock('./hooks/useGameLoop', () => ({ useGameLoop: vi.fn() }))

function seat(patch = {}) {
  // 주문·노가다 패널은 세션 없이는 그리지 않는다.
  useGameStore.getState().setSession('s1')
  useGameStore.getState().applySnapshot({ ...baseSnapshot(), ...patch }, 1)
}

beforeEach(() => {
  useGameStore.getState().reset()
  useUiStore.setState({ tab: 'news', selected: 'hanbit' })
})

describe('판 껍데기', () => {
  it('차트와 주문은 어느 탭에서도 보인다', async () => {
    seat()
    render(<Board />)
    expect(screen.getByRole('heading', { name: /주문/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '기업' }))
    expect(screen.getByRole('heading', { name: /주문/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '내 포지션' }))
    expect(screen.getByRole('heading', { name: /주문/ })).toBeInTheDocument()
  })

  it('탭을 바꾸면 좌측 내용이 바뀐다', async () => {
    seat()
    render(<Board />)
    expect(screen.getByRole('heading', { name: '뉴스' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '기업' }))
    expect(screen.queryByRole('heading', { name: '뉴스' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /기업분석/ })).toBeInTheDocument()
  })

  it('파산하면 탭과 무관하게 복귀 수단이 뜨고 주문은 사라진다', async () => {
    seat({ bankrupt: true, cash: 0, equity: 50_000 })
    render(<Board />)
    expect(screen.getByRole('heading', { name: '파산' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /주문/ })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: '기업' }))
    expect(screen.getByRole('heading', { name: '파산' })).toBeInTheDocument()
  })

  it('파산이 아니면 파산 패널은 안 보인다', () => {
    seat()
    render(<Board />)
    expect(screen.queryByRole('heading', { name: '파산' })).not.toBeInTheDocument()
  })

  it('티커에서 종목을 고르면 주문이 따라간다', async () => {
    seat()
    render(<Board />)
    expect(screen.getByRole('heading', { name: /주문 · 한빛솔리드/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /제노셀/ }))
    expect(screen.getByRole('heading', { name: /주문 · 제노셀/ })).toBeInTheDocument()
  })

  it('탭을 옮겨도 폴링 훅은 계속 걸려 있다 — 시장이 멈추면 안 된다', async () => {
    const { useGameLoop } = await import('./hooks/useGameLoop')
    seat()
    render(<Board />)
    await userEvent.click(screen.getByRole('tab', { name: '내 포지션' }))
    expect(useGameLoop).toHaveBeenCalled()
  })
})
