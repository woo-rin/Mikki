/**
 * 서버가 주는 age_seconds 는 그 스냅샷 시점의 상대값이다.
 * since 로 새 기사만 받으면 이 값이 갱신되지 않으므로,
 * 받은 순간에 절대 tick 으로 바꿔 두고 매번 다시 계산한다.
 */
export function publishTick(snapshotTick: number, ageSeconds: number): number {
  return snapshotTick - ageSeconds
}

export function ageAt(currentTick: number, publishTick: number): number {
  return Math.max(0, currentTick - publishTick)
}

/**
 * analyze 응답에는 tick 이 없으므로 수신 직후의 최신 스냅샷 tick 을 기준으로 쓴다.
 * ramp_remaining 이 0 이면 끝난 기회다 — 끝 tick 을 만들지 않는다.
 */
export function rampEndTick(currentTick: number, rampRemaining: number): number | null {
  return rampRemaining > 0 ? currentTick + rampRemaining : null
}

export function rampRemainingAt(currentTick: number, endTick: number | null): number {
  if (endTick === null) return 0
  return Math.max(0, endTick - currentTick)
}
