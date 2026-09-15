/**
 * docs/api.md §4 를 그대로 옮긴 것이다.
 * 서버가 커질 때(펀더멘털·AI 참가자) 넓어지는 파일은 여기 하나여야 한다.
 * 타입에 없는 필드는 런타임에 무시되므로, 서버가 더 줘도 화면은 깨지지 않는다.
 */

export type Symbol_ = 'hanbit' | 'geno' | 'sungjin' | 'pixel' | 'taesan' | 'arawings'

export type Strength = 'up_strong' | 'up_weak' | 'none' | 'down_weak' | 'down_strong'

export type Valuation =
  | 'severely_overvalued'
  | 'overvalued'
  | 'fair'
  | 'undervalued'
  | 'severely_undervalued'

export interface Stock {
  symbol: Symbol_
  name: string
  sector: string
  price: number
  /** 시작가 대비 등락률. 표시 전용 — 어떤 판정에도 쓰지 않는다. */
  change_pct: number
  held: number
  /** 이 라운드에 이 종목의 적정가를 샀는지. 뉴스의 analyzed 와 이름이 다르다 — 별개 자원이다. */
  fundamentals_analyzed: boolean
  /** 최근 60틱의 가격. 오래된 것이 앞이고 마지막 값이 price 와 같다. 서버가 들고 있다. */
  history: number[]
  /** 수수료를 포함한 취득 단가(내림). **안 들고 있으면 null** — 0 이 아니다. */
  avg_cost: number | null
}

export interface NewsItem {
  news_id: number
  symbol: Symbol_
  name: string
  sector: string
  headline: string
  body: string
  age_seconds: number
  analyzed: boolean
  commentary: string
  offline: boolean
}

export interface Snapshot {
  session_id: string
  tick: number
  round_no: number
  cash: number
  equity: number
  target: number
  round_start_equity: number
  analyses_left: number
  /** 남은 기업분석 횟수 (0~2). AI 분석과 별개 풀이다. */
  company_analyses_left: number
  bankrupt: boolean
  locked: boolean
  lock_remaining: number
  grind_count: number
  goal_reached: boolean
  stocks: Stock[]
  news: NewsItem[]
  news_total: number
}

export interface TradeResult {
  side: 'buy' | 'sell'
  symbol: Symbol_
  qty: number
  /** 서버가 체결한 가격. 프론트가 보던 가격과 다를 수 있다. */
  price: number
  gross: number
  fee: number
  cash: number
  equity: number
}

export interface AnalyzeResult {
  news_id: number
  strength: Strength
  label: string
  commentary: string
  ramp_remaining: number
  already_priced_in: boolean
  offline: boolean
  analyses_left: number
}

export interface Financials {
  quarter: string
  revenue: number
  operating_income: number
  net_income: number
  eps: number
  /** 적자 분기에는 null 이다. 그때 적정가는 PER 이 아니라 매출 기준(PSR)으로 냈다. */
  per: number | null
  debt_ratio: number
}

export interface CompanyAnalysisResult {
  symbol: Symbol_
  name: string
  /** 그 라운드의 적정가. 스냅샷에는 없다 — 이 응답으로만 나온다. */
  fair_value: number
  current_price: number
  /** (current_price - fair_value) / fair_value × 100. 양수가 고평가. */
  gap_pct: number
  valuation: Valuation
  /** 한국어 등급 라벨. 프론트에서 다시 만들지 않는다. */
  label: string
  financials: Financials
  commentary: string
  offline: boolean
  company_analyses_left: number
}

export interface GrindResult {
  payout: number
  lock_remaining: number
  grind_count: number
}
