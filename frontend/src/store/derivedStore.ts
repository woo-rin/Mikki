import { create } from 'zustand'
import type { AnalyzeResult, CompanyAnalysisResult, Snapshot } from '../api/types'
import type { TradeRow } from '../api/types'
import { type FeedItem, appendTrades, attachAnalysis, upsertNews } from './merge'

/**
 * 새로고침하면 사라지는 것들만 담는다.
 * 가격 이력과 평단은 여기 없다 — 서버가 stocks[].history 와 avg_cost 로 준다 (api.md §6).
 */
interface DerivedState {
  feed: FeedItem[]
  /** 체결은 증분으로 온다(trades_since). 누적은 여기서만 한다. */
  trades: TradeRow[]
  /** 산 종목의 적정가와 등급. 스냅샷에 없으므로 여기서만 산다. */
  valuations: Record<string, CompanyAnalysisResult>
  /** 라운드가 바뀐 것을 알아보기 위한 표식 */
  roundNo: number | null

  record: (snap: Snapshot) => void
  recordAnalysis: (res: AnalyzeResult, tick: number) => void
  recordValuation: (res: CompanyAnalysisResult) => void
  reset: () => void
}

export const useDerivedStore = create<DerivedState>((set) => ({
  feed: [],
  trades: [],
  valuations: {},
  roundNo: null,

  record: (snap) =>
    set((s) => {
      // 라운드 N 은 N분기 실적을 본다. 라운드가 넘어가면 적정가가 움직이므로
      // 지난 라운드에 산 값은 틀린 정보다. 서버도 fundamentals_analyzed 를 리셋한다.
      const rolled = s.roundNo !== null && s.roundNo !== snap.round_no
      return {
        feed: upsertNews(s.feed, snap),
        trades: appendTrades(s.trades, snap.trades),
        valuations: rolled ? {} : s.valuations,
        roundNo: snap.round_no,
      }
    }),

  recordAnalysis: (res, tick) => set((s) => ({ feed: attachAnalysis(s.feed, res, tick) })),

  recordValuation: (res) =>
    set((s) => ({ valuations: { ...s.valuations, [res.symbol]: res } })),

  reset: () => set({ feed: [], trades: [], valuations: {}, roundNo: null }),
}))
