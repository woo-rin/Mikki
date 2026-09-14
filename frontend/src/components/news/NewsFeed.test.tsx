import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, capturedAnalyze, sampleNews } from '../../mocks/fixtures'
import { server } from '../../mocks/server'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { Toasts } from '../system/Toasts'
import { NewsFeed } from './NewsFeed'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useUiStore.setState({ toasts: [] })
  useGameStore.getState().setSession('s')
})

function seed(tick = 200) {
  const snap = baseSnapshot({ tick, news: [sampleNews()] })
  useGameStore.getState().applySnapshot(snap, 1)
  useDerivedStore.getState().record(snap)
}

describe('뉴스 피드', () => {
  it('아직 기사가 없으면 오류가 아니라 대기 상태다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ news: [] }), 1)
    render(<NewsFeed />)
    expect(screen.getByText('첫 기사를 기다리는 중…')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('헤드라인·종목·경과 시간·오프라인 배지를 보여준다', () => {
    seed()
    render(<NewsFeed />)
    expect(screen.getByText(/픽셀로그 생산 라인 일시 중단/)).toBeInTheDocument()
    expect(screen.getByText('188초 전')).toBeInTheDocument()
    expect(screen.getByText('로컬')).toBeInTheDocument()
  })

  it('경과 시간이 tick 을 따라 흐른다 — 서버가 다시 보내주지 않아도', () => {
    seed(200)
    const { rerender } = render(<NewsFeed />)
    useGameStore.getState().applySnapshot(baseSnapshot({ tick: 260, news: [] }), 2)
    rerender(<NewsFeed />)
    expect(screen.getByText('248초 전')).toBeInTheDocument()
  })

  it('미분석 기사에는 방향 색도 판정도 없다', () => {
    seed()
    render(<NewsFeed />)
    const card = screen.getByTestId('news-0')
    expect(card.className).not.toMatch(/\b(up|down)\b/)
    expect(card.querySelector('.up')).toBeNull()
    expect(card.querySelector('.down')).toBeNull()
    expect(screen.getByText('미분석')).toBeInTheDocument()
  })

  it('분석하면 판정과 해설이 붙고 잔여 횟수가 준다', async () => {
    seed()
    render(<NewsFeed />)
    await userEvent.click(screen.getByRole('button', { name: '분석' }))
    expect(await screen.findByText('무영향')).toBeInTheDocument()
    expect(screen.getByText(/이미 알려진 내용의 재인용/)).toBeInTheDocument()
    expect(useGameStore.getState().snapshot?.analyses_left).toBe(4)
  })

  it('이미 반영된 기사는 남은 창이 없다고 말한다', async () => {
    seed()
    render(<NewsFeed />)
    await userEvent.click(screen.getByRole('button', { name: '분석' }))
    expect(await screen.findByText('이미 반영됨')).toBeInTheDocument()
  })

  it('잔여 0 이면 분석 버튼이 잠긴다', () => {
    const snap = baseSnapshot({ tick: 200, news: [sampleNews()], analyses_left: 0 })
    useGameStore.getState().applySnapshot(snap, 1)
    useDerivedStore.getState().record(snap)
    render(<NewsFeed />)
    expect(screen.getByRole('button', { name: '분석' })).toBeDisabled()
  })

  it('분석 오류는 서버 문장 그대로 알린다', async () => {
    seed()
    server.use(
      http.post('/api/analyze', () =>
        HttpResponse.json(
          { detail: { code: 'no_analyses_left', message: '이번 라운드 분석을 모두 썼습니다.' } },
          { status: 400 },
        ),
      ),
    )
    render(<><NewsFeed /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '분석' }))
    await screen.findByRole('alert')
    expect(useUiStore.getState().toasts[0]?.text).toBe('이번 라운드 분석을 모두 썼습니다.')
  })

  it('분석 응답의 등급이 그대로 쓰인다', async () => {
    seed()
    server.use(
      http.post('/api/analyze', () =>
        HttpResponse.json({
          ...capturedAnalyze,
          strength: 'down_strong',
          label: '강한 하락',
          ramp_remaining: 40,
          already_priced_in: false,
        }),
      ),
    )
    render(<NewsFeed />)
    await userEvent.click(screen.getByRole('button', { name: '분석' }))
    expect(await screen.findByText('강한 하락')).toHaveClass('down')
    expect(screen.getByText('남은 창 40초')).toBeInTheDocument()
  })
})
