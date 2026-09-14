export function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

/** 손익용. 모르면 — 를 돌려준다. */
export function signedWon(n: number | null): string {
  if (n === null) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toLocaleString('ko-KR')}원`
}

export function pct(n: number): string {
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}
