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

/** 재무 숫자는 억 단위로 줄인다. 원 단위로 쓰면 자릿수가 읽히지 않는다. */
export function eok(n: number): string {
  const v = n / 1e8
  const shown = Math.abs(v) >= 10 ? Math.round(v) : Math.round(v * 10) / 10
  return `${shown.toLocaleString('ko-KR')}억`
}
