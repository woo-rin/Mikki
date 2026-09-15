import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'
import { capturedCompanyAnalysis } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { ApiError } from './client'
import { analyze, companyAnalysis, getState, grind, newGame, trade } from './endpoints'

describe('엔드포인트', () => {
  it('새 게임은 시작 스냅샷을 준다 — 뉴스는 빈 배열이 정상이다', async () => {
    const snap = await newGame()
    expect(snap.cash).toBe(1_000_000)
    expect(snap.target).toBe(3_000_000)
    expect(snap.analyses_left).toBe(5)
    expect(snap.news).toEqual([])
  })

  it('상태 폴링은 since 를 쿼리로 보낸다', async () => {
    let seen: string | null = null
    server.use(
      http.get('/api/state', ({ request }) => {
        seen = new URL(request.url).searchParams.get('since')
        return HttpResponse.json({ session_id: 's', tick: 3 })
      }),
    )
    await getState('s', 7)
    expect(seen).toBe('7')
  })

  it('체결은 서버가 정한 가격을 그대로 돌려준다', async () => {
    const res = await trade('s', 'geno', 'buy', 2)
    expect(res.price).toBe(44_618)
    expect(res.fee).toBe(178)
    expect(res.cash).toBe(910_586)
  })

  it('분석은 등급과 남은 램프를 준다', async () => {
    const res = await analyze('s', 0)
    expect(res.strength).toBe('none')
    expect(res.label).toBe('무영향')
    expect(res.analyses_left).toBe(4)
  })

  it('노가다는 보수와 잠금 시간을 준다', async () => {
    const res = await grind('s')
    expect(res.payout).toBe(200_000)
    expect(res.lock_remaining).toBe(120)
  })


  it('기업분석은 적정가와 밸류에이션 등급을 준다', async () => {
    const res = await companyAnalysis('s', 'geno')
    expect(res.fair_value).toBe(39_216)
    expect(res.current_price).toBe(47_909)
    expect(res.gap_pct).toBe(22.2)
    expect(res.valuation).toBe('overvalued')
    expect(res.label).toBe('고평가')
    expect(res.company_analyses_left).toBe(1)
  })

  it('기업분석은 분기 재무를 함께 준다', async () => {
    const res = await companyAnalysis('s', 'geno')
    expect(res.financials.quarter).toBe('2024Q1')
    expect(res.financials.eps).toBe(1032)
    expect(res.financials.per).toBe(46.4)
    expect(res.financials.debt_ratio).toBe(40.0)
  })

  it('기업분석은 심볼을 본문에 보낸다', async () => {
    let seen: unknown = null
    server.use(
      http.post('/api/company-analysis', async ({ request }) => {
        seen = await request.json()
        return HttpResponse.json(capturedCompanyAnalysis)
      }),
    )
    await companyAnalysis('s', 'taesan')
    expect(seen).toEqual({ session_id: 's', symbol: 'taesan' })
  })

  it('오류는 ApiError 로 던진다', async () => {
    server.use(
      http.post('/api/trade', () =>
        HttpResponse.json(
          { detail: { code: 'insufficient_cash', message: '현금이 부족합니다.' } },
          { status: 400 },
        ),
      ),
    )
    await expect(trade('s', 'geno', 'buy', 999)).rejects.toMatchObject({
      code: 'insufficient_cash',
      status: 400,
    })
    await expect(trade('s', 'geno', 'buy', 999)).rejects.toBeInstanceOf(ApiError)
  })
})
