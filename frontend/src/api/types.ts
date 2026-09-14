/**
 * docs/api.md §4 를 그대로 옮긴 것이다.
 * 서버가 커질 때(펀더멘털·AI 참가자) 넓어지는 파일은 여기 하나여야 한다.
 * 타입에 없는 필드는 런타임에 무시되므로, 서버가 더 줘도 화면은 깨지지 않는다.
 */

export type Symbol_ = 'hanbit' | 'geno' | 'sungjin' | 'pixel' | 'taesan' | 'arawings'

export type Strength = 'up_strong' | 'up_weak' | 'none' | 'down_weak' | 'down_strong'

export interface Stock {
  symbol: Symbol_
  name: string
  sector: string
  price: number
  /** 시작가 대비 등락률. 표시 전용 — 어떤 판정에도 쓰지 않는다. */
  change_pct: number
  held: number
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

export interface GrindResult {
  payout: number
  lock_remaining: number
  grind_count: number
}
