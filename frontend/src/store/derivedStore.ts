import { create } from 'zustand'
import type { AnalyzeResult, Snapshot, TradeResult } from '../api/types'
import { type Position, applyBuy, applySell, emptyPosition } from '../lib/money'
import { type FeedItem, type PricePoint, appendHistory, attachAnalysis, upsertNews } from './merge'

/**
 * 새로고침하면 사라지는 것들만 담는다.
 * 서버가 주지 않아 프론트가 직접 쌓아야 하는 값들이다 (api.md §6).
 */
interface DerivedState {
  history: Record<string, PricePoint[]>
  feed: FeedItem[]
  positions: Record<string, Position>

  record: (snap: Snapshot) => void
  recordFill: (res: TradeResult) => void
  recordAnalysis: (res: AnalyzeResult, tick: number) => void
  reset: () => void
}

export const useDerivedStore = create<DerivedState>((set) => ({
  history: {},
  feed: [],
  positions: {},

  record: (snap) =>
    set((s) => ({
      history: appendHistory(s.history, snap),
      feed: upsertNews(s.feed, snap),
    })),

  recordFill: (res) =>
    set((s) => {
      const prev = s.positions[res.symbol] ?? emptyPosition()
      const next =
        res.side === 'buy'
          ? applyBuy(prev, res.price, res.qty)
          : applySell(prev, res.price, res.qty)
      return { positions: { ...s.positions, [res.symbol]: next } }
    }),

  recordAnalysis: (res, tick) => set((s) => ({ feed: attachAnalysis(s.feed, res, tick) })),

  reset: () => set({ history: {}, feed: [], positions: {} }),
}))
