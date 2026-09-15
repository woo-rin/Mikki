import { describe, expect, it } from 'vitest'
import {
  baseSnapshot, capturedAnalyze, capturedCompanyAnalysis, capturedTrade, sampleNews,
} from '../mocks/fixtures'
import {
  applyCompanyAnalysisToSnapshot, applyGrindToSnapshot, applyTradeToSnapshot,
  attachAnalysis, isFresher, maxNewsId, positionRows, priceSeries, upsertNews,
} from './merge'

describe('가격 이력 — 서버가 준 배열에 tick 좌표를 입힌다', () => {
  const stock = (history: number[], price: number) => ({
    symbol: 'hanbit' as const, name: '한빛솔리드', sector: '반도체',
    price, change_pct: 0, held: 0, fundamentals_analyzed: false,
    avg_cost: null, history,
  })

  it('마지막 값이 현재 tick 이다', () => {
    const series = priceSeries(stock([100, 101, 102], 102), 42)
    expect(series[series.length - 1]).toEqual({ tick: 42, price: 102 })
  })

  it('오래된 것이 앞이고 tick 이 1씩 거슬러 올라간다', () => {
    expect(priceSeries(stock([100, 101, 102], 102), 42)).toEqual([
      { tick: 40, price: 100 },
      { tick: 41, price: 101 },
      { tick: 42, price: 102 },
    ])
  })

  it('tick 0 에 이력이 비어 있어도 깨지지 않는다', () => {
    expect(priceSeries(stock([], 82_000), 0)).toEqual([])
  })

  it('한 점만 있어도 그 점의 tick 은 현재다', () => {
    expect(priceSeries(stock([82_000], 82_000), 7)).toEqual([{ tick: 7, price: 82_000 }])
  })

  it('60틱이 꽉 차면 가장 오래된 것이 tick-59 다', () => {
    const sixty = Array.from({ length: 60 }, (_, i) => 1000 + i)
    const series = priceSeries(stock(sixty, 1059), 200)
    expect(series).toHaveLength(60)
    expect(series[0]).toEqual({ tick: 141, price: 1000 })
    expect(series[59]).toEqual({ tick: 200, price: 1059 })
  })
})

describe('뉴스 누적', () => {
  it('news_id 기준으로 upsert 한다', () => {
    const first = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(first).toHaveLength(1)

    const again = upsertNews(
      first,
      baseSnapshot({ tick: 260, news: [sampleNews({ headline: '고쳐진 제목' })] }),
    )
    expect(again).toHaveLength(1)
    expect(again[0]?.headline).toBe('고쳐진 제목')
  })

  it('수신 시각을 절대 tick 으로 고정한다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(feed[0]?.publishTick).toBe(12) // 200 - 188
  })

  it('새 기사는 앞에 붙는다', () => {
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 1 })] }),
    )
    expect(feed.map((f) => f.newsId)).toEqual([1, 0])
  })

  it('새 기사가 없으면 같은 배열을 돌려준다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(upsertNews(feed, baseSnapshot({ tick: 260, news: [] }))).toBe(feed)
  })

  it('since 커서는 받은 최대 news_id 다. 아직 없으면 -1', () => {
    expect(maxNewsId([])).toBe(-1)
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 4 })] }),
    )
    expect(maxNewsId(feed)).toBe(4)
  })
})

describe('분석 병합', () => {
  it('해당 기사에만 붙는다', () => {
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 1 })] }),
    )
    const next = attachAnalysis(feed, capturedAnalyze, 300)
    expect(next.find((f) => f.newsId === 0)?.analysis?.label).toBe('무영향')
    expect(next.find((f) => f.newsId === 1)?.analysis).toBeNull()
  })

  it('이미 반영된 기사는 램프 끝 tick 을 만들지 않는다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 300, news: [sampleNews()] }))
    const next = attachAnalysis(feed, capturedAnalyze, 300) // ramp_remaining 0
    expect(next[0]?.analysis?.rampEndTick).toBeNull()
  })

  it('남은 램프가 있으면 끝 tick 을 고정한다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 300, news: [sampleNews()] }))
    const next = attachAnalysis(
      feed,
      { ...capturedAnalyze, strength: 'up_strong', ramp_remaining: 40, already_priced_in: false },
      300,
    )
    expect(next[0]?.analysis?.rampEndTick).toBe(340)
  })
})

describe('시퀀스 가드', () => {
  it('더 새로운 응답만 받는다', () => {
    expect(isFresher(3, 4)).toBe(true)
    expect(isFresher(3, 3)).toBe(false)
    expect(isFresher(3, 2)).toBe(false) // 순서가 뒤바뀐 응답
  })
})

describe('보유 행', () => {
  const withGeno = (patch: Record<string, unknown>) =>
    baseSnapshot({
      stocks: baseSnapshot().stocks.map((s) =>
        s.symbol === 'geno' ? { ...s, ...patch } : s,
      ),
    })

  it('보유가 없는 종목은 빠진다', () => {
    expect(positionRows(baseSnapshot())).toEqual([])
  })

  it('서버가 준 avg_cost 를 그대로 쓴다', () => {
    const rows = positionRows(withGeno({ held: 3, price: 50_000, avg_cost: 45_090 }))
    expect(rows).toHaveLength(1)
    expect(rows[0]?.avg).toBe(45_090)
    expect(rows[0]?.unrealized).toBe((50_000 - 45_090) * 3)
  })

  it('avg_cost 가 null 이면 손익도 null 이다', () => {
    const rows = positionRows(withGeno({ held: 3, price: 50_000, avg_cost: null }))
    expect(rows[0]?.avg).toBeNull()
    expect(rows[0]?.unrealized).toBeNull()
  })
})

describe('액션 응답 반영', () => {
  it('체결은 응답의 현금·총자산을 그대로 쓴다', () => {
    const next = applyTradeToSnapshot(baseSnapshot(), capturedTrade)
    expect(next.cash).toBe(910_586)
    expect(next.equity).toBe(999_822)
  })

  it('노가다 보수는 현금에 즉시 더해지지 않는다', () => {
    const snap = baseSnapshot({ cash: 50_000, bankrupt: true })
    const next = applyGrindToSnapshot(snap, {
      payout: 200_000, lock_remaining: 120, grind_count: 1,
    })
    expect(next.cash).toBe(50_000) // 잠금이 끝난 뒤 폴링으로 들어온다
    expect(next.locked).toBe(true)
    expect(next.lock_remaining).toBe(120)
    expect(next.grind_count).toBe(1)
  })
})

describe('기업분석 반영', () => {
  it('잔여 횟수를 응답대로 쓴다', () => {
    const next = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    expect(next.company_analyses_left).toBe(1)
  })

  it('그 종목만 분석됨으로 표시한다', () => {
    const next = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    expect(next.stocks.find((s) => s.symbol === 'geno')?.fundamentals_analyzed).toBe(true)
    expect(next.stocks.find((s) => s.symbol === 'hanbit')?.fundamentals_analyzed).toBe(false)
  })

  it('같은 종목을 다시 사면 서버가 횟수를 안 깎는다 — 응답을 그대로 믿는다', () => {
    const once = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    const twice = applyCompanyAnalysisToSnapshot(once, capturedCompanyAnalysis)
    expect(twice.company_analyses_left).toBe(1)
  })
})
