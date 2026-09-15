import { HttpResponse, http } from 'msw'
import {
  baseSnapshot, capturedAnalyze, capturedCompanyAnalysis, capturedTrade,
} from './fixtures'

export const handlers = [
  http.post('/api/game', () => HttpResponse.json(baseSnapshot())),
  http.get('/api/state', () => HttpResponse.json(baseSnapshot())),
  http.post('/api/trade', () => HttpResponse.json(capturedTrade)),
  http.post('/api/analyze', () => HttpResponse.json(capturedAnalyze)),
  http.post('/api/company-analysis', () => HttpResponse.json(capturedCompanyAnalysis)),
  http.post('/api/grind', () =>
    HttpResponse.json({ payout: 200_000, lock_remaining: 120, grind_count: 1 }),
  ),
]
