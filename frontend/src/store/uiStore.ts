import { create } from 'zustand'
import type { Symbol_ } from '../api/types'

export interface Toast {
  id: number
  text: string
  tone: 'error' | 'info'
}

interface UiState {
  selected: Symbol_
  toasts: Toast[]
  select: (s: Symbol_) => void
  pushToast: (text: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
}

let nextToastId = 1

export const useUiStore = create<UiState>((set) => ({
  selected: 'hanbit',
  toasts: [],

  select: (s) => set({ selected: s }),

  pushToast: (text, tone = 'error') =>
    set((s) => ({ toasts: [...s.toasts, { id: nextToastId++, text, tone }] })),

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
