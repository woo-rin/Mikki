import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  baseSnapshot, capturedCompanyAnalysis, capturedLossQuarter,
} from '../../mocks/fixtures'
import { server } from '../../mocks/server'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { Toasts } from '../system/Toasts'
import { FundamentalsPanel } from './FundamentalsPanel'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useUiStore.setState({ selected: 'geno', toasts: [] })
  useGameStore.getState().setSession('s')
  useGameStore.getState().applySnapshot(baseSnapshot(), 1)
})

describe('기업분석 패널 — 사기 전', () => {
  it('적정가도 등급도 보여주지 않는다', () => {
    render(<FundamentalsPanel />)
    expect(screen.queryByText(/39,216/)).not.toBeInTheDocument()
    expect(screen.queryByText('고평가')).not.toBeInTheDocument()
    expect(screen.queryByText(/2024Q1/)).not.toBeInTheDocument()
  })

  it('잔여 횟수와 분석 버튼만 보여준다', () => {
    render(<FundamentalsPanel />)
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '기업분석' })).toBeEnabled()
  })

  it('잔여 0 이면 버튼이 죽는다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ company_analyses_left: 0 }), 2)
    render(<FundamentalsPanel />)
    expect(screen.getByRole('button', { name: '기업분석' })).toBeDisabled()
  })
})

describe('기업분석 패널 — 사고 나서', () => {
  it('적정가·괴리율·등급 라벨을 서버가 준 대로 보여준다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    expect(await screen.findByText('39,216원')).toBeInTheDocument()
    expect(screen.getByText('+22.20%')).toBeInTheDocument()
    expect(screen.getByText('고평가')).toBeInTheDocument()
  })

  it('분기 재무를 보여준다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    expect(await screen.findByText('2024Q1')).toBeInTheDocument()
    expect(screen.getByText('812억')).toBeInTheDocument()
    expect(screen.getByText('46.4')).toBeInTheDocument()
    expect(screen.getByText('1,032원')).toBeInTheDocument()
  })

  it('해설과 로컬 배지를 보여준다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    expect(await screen.findByText(/바이오 섹터 기준 배수를 웃돈다/)).toBeInTheDocument()
    expect(screen.getByText('로컬')).toBeInTheDocument()
  })

  it('잔여 횟수가 응답대로 준다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    await screen.findByText('39,216원')
    expect(useGameStore.getState().snapshot?.company_analyses_left).toBe(1)
  })

  it('같은 종목을 다시 사도 횟수가 안 깎인다 — 서버 응답을 그대로 믿는다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    await screen.findByText('39,216원')
    await userEvent.click(screen.getByRole('button', { name: '다시 조회' }))
    await screen.findByText('39,216원')
    expect(useGameStore.getState().snapshot?.company_analyses_left).toBe(1)
  })
})

describe('기업분석 패널 — 적자 분기', () => {
  it('per 이 null 이어도 깨지지 않고 PSR 로 냈다는 사정을 비춘다', async () => {
    server.use(
      http.post('/api/company-analysis', () => HttpResponse.json(capturedLossQuarter)),
    )
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    expect(await screen.findByText('심각한 저평가')).toBeInTheDocument()
    expect(screen.getByText(/적자 분기/)).toBeInTheDocument()
    expect(screen.getByText(/매출 기준/)).toBeInTheDocument()
    expect(screen.getByText('-24억')).toBeInTheDocument()
  })
})

describe('기업분석 패널 — 새 판과 오류', () => {
  it('새 판이 시작되면 산 값이 사라지고 다시 사야 한다', async () => {
    render(<FundamentalsPanel />)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    await screen.findByText('39,216원')

    const next = baseSnapshot({ session_id: 'other', company_analyses_left: 2 })
    act(() => {
      useGameStore.getState().forceSnapshot(next)
      useDerivedStore.getState().record(next)
    })

    expect(screen.queryByText('39,216원')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '기업분석' })).toBeInTheDocument()
  })

  it('소진 오류는 서버 문장 그대로 토스트로 뜬다', async () => {
    server.use(
      http.post('/api/company-analysis', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'no_company_analyses_left',
              message: '이번 라운드 기업분석을 모두 썼습니다.',
            },
          },
          { status: 400 },
        ),
      ),
    )
    render(<><FundamentalsPanel /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '기업분석' }))
    await screen.findByRole('alert')
    expect(useUiStore.getState().toasts[0]?.text).toBe('이번 라운드 기업분석을 모두 썼습니다.')
  })

  it('선택 종목을 바꾸면 그 종목의 보관분을 보여준다', async () => {
    // 실제로 사면 서버 스냅샷의 fundamentals_analyzed 와 보관소가 함께 세워진다
    const bought = baseSnapshot({
      stocks: baseSnapshot().stocks.map((x) =>
        x.symbol === 'geno' ? { ...x, fundamentals_analyzed: true } : x,
      ),
    })
    useGameStore.getState().applySnapshot(bought, 2)
    useDerivedStore.getState().record(bought)
    useDerivedStore.getState().recordValuation(capturedCompanyAnalysis)
    render(<FundamentalsPanel />)
    expect(screen.getByText('39,216원')).toBeInTheDocument()

    act(() => useUiStore.getState().select('hanbit'))
    expect(screen.queryByText('39,216원')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '기업분석' })).toBeInTheDocument()
  })
})
