import type {
  AnalyzeResult, CompanyAnalysisResult, NewsItem, Snapshot, Stock, TradeResult,
} from '../api/types'

/**
 * 테스트용 고정값이다. 실제 시작가는 판마다 달라지므로
 * 이 숫자를 "그 종목의 시작가" 로 읽으면 안 된다.
 */
export const SYMBOLS: Stock[] = [
  { symbol: 'hanbit', name: '한빛솔리드', sector: '반도체', price: 82_000, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
  { symbol: 'geno', name: '제노셀', sector: '바이오', price: 45_000, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
  { symbol: 'sungjin', name: '성진셀즈', sector: '2차전지', price: 61_000, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
  { symbol: 'pixel', name: '픽셀로그', sector: '게임', price: 33_000, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
  { symbol: 'taesan', name: '태산건영', sector: '건설', price: 18_500, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
  { symbol: 'arawings', name: '아라윙스', sector: '항공', price: 24_000, change_pct: 0, held: 0, fundamentals_analyzed: false, history: [] },
]

export function baseSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    session_id: 'test-session',
    tick: 0,
    round_no: 1,
    cash: 1_000_000,
    equity: 1_000_000,
    target: 3_000_000,
    round_start_equity: 1_000_000,
    analyses_left: 5,
    company_analyses_left: 2,
    bankrupt: false,
    locked: false,
    lock_remaining: 0,
    grind_count: 0,
    goal_reached: false,
    stocks: SYMBOLS.map((s) => ({ ...s })),
    news: [],
    news_total: 20,
    ...overrides,
  }
}

export function sampleNews(overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    news_id: 0,
    symbol: 'pixel',
    name: '픽셀로그',
    sector: '게임',
    headline: '픽셀로그 생산 라인 일시 중단… 출하 지연 우려',
    body: '업계는 게임 업황 조정 국면의 일부로 보고 있으나 …',
    age_seconds: 188,
    analyzed: false,
    commentary: '',
    offline: true,
    ...overrides,
  }
}

/** api.md §3 의 실제 캡처 */
export const capturedTrade: TradeResult = {
  side: 'buy', symbol: 'geno', qty: 2, price: 44_618,
  gross: 89_236, fee: 178, cash: 910_586, equity: 999_822,
}

/** api.md §3 의 실제 캡처 */
export const capturedAnalyze: AnalyzeResult = {
  news_id: 0,
  strength: 'none',
  label: '무영향',
  commentary: '이미 알려진 내용의 재인용이거나 규모가 미미하다. 판정: 무영향. …',
  ramp_remaining: 0,
  already_priced_in: true,
  offline: true,
  analyses_left: 4,
}

/** api.md §3 의 실제 캡처 */
export const capturedCompanyAnalysis: CompanyAnalysisResult = {
  symbol: 'geno',
  name: '제노셀',
  fair_value: 39_216,
  current_price: 47_909,
  gap_pct: 22.2,
  valuation: 'overvalued',
  label: '고평가',
  financials: {
    quarter: '2024Q1',
    revenue: 81_200_000_000,
    operating_income: 16_500_000_000,
    net_income: 12_800_000_000,
    eps: 1032,
    per: 46.4,
    debt_ratio: 40.0,
  },
  commentary: '제노셀 은 바이오 섹터 기준 배수를 웃돈다. 판정: 고평가. …',
  offline: true,
  company_analyses_left: 1,
}

/** 적자 분기. per 이 null 이고 적정가는 PSR 로 냈다. */
export const capturedLossQuarter: CompanyAnalysisResult = {
  ...capturedCompanyAnalysis,
  fair_value: 52_000,
  current_price: 39_000,
  gap_pct: -25.0,
  valuation: 'severely_undervalued',
  label: '심각한 저평가',
  financials: {
    quarter: '2024Q3',
    revenue: 74_500_000_000,
    operating_income: -3_100_000_000,
    net_income: -2_400_000_000,
    eps: -193,
    per: null,
    debt_ratio: 52.8,
  },
  commentary: '체력 대비 주가가 크게 눌려 있다. 판정: 심각한 저평가. …',
  company_analyses_left: 0,
}
