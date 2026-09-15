import { create } from 'zustand'
import type { Symbol_ } from '../api/types'

export interface Toast {
  id: number
  text: string
  tone: 'error' | 'info'
}

/** 좌측에서 한 번에 하나만 본다. 급한 것(파산·라운드)은 여기 들어가지 않는다. */
export type Tab = 'news' | 'fundamentals' | 'participants' | 'positions'

interface UiState {
  selected: Symbol_
  tab: Tab
  toasts: Toast[]
  select: (s: Symbol_) => void
  setTab: (t: Tab) => void
  pushToast: (text: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
}

let nextToastId = 1

export const useUiStore = create<UiState>((set) => ({
  selected: 'hanbit',
  tab: 'news',
  toasts: [],

  select: (s) => set({ selected: s }),

  setTab: (t) => set({ tab: t }),

  pushToast: (text, tone = 'error') =>
    set((s) => ({ toasts: [...s.toasts, { id: nextToastId++, text, tone }] })),

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
