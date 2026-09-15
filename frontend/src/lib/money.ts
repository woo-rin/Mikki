/** 서버와 같은 수수료율. 매수·매도 양방향으로 부과된다. */
export const FEE_RATE = 0.002

/** 체결금액의 0.2%, 내림. 서버도 내림이므로 반드시 맞춰야 한다. */
export function fee(price: number, qty: number): number {
  return Math.floor(price * qty * FEE_RATE)
}

export function buyCost(price: number, qty: number): number {
  return price * qty + fee(price, qty)
}

export function sellNet(price: number, qty: number): number {
  return price * qty - fee(price, qty)
}

/**
 * 현금으로 살 수 있는 최대 수량.
 * 내림 때문에 닫힌 식이 정확하지 않으므로 근사한 뒤 양방향으로 보정한다.
 */
export function maxBuyQty(cash: number, price: number): number {
  if (price <= 0 || cash <= 0) return 0
  let q = Math.max(0, Math.floor(cash / (price * (1 + FEE_RATE))))
  while (buyCost(price, q + 1) <= cash) q += 1
  while (q > 0 && buyCost(price, q) > cash) q -= 1
  return q
}

export interface Position {
  qty: number
  /** 매수 수수료를 포함한 취득 단가, 내림. 0 은 "모른다" 를 뜻한다. */
  avg: number
  realized: number
}

export function emptyPosition(): Position {
  return { qty: 0, avg: 0, realized: 0 }
}

export function applyBuy(pos: Position, price: number, qty: number): Position {
  const nextQty = pos.qty + qty
  const total = pos.avg * pos.qty + buyCost(price, qty)
  return { qty: nextQty, avg: Math.floor(total / nextQty), realized: pos.realized }
}

export function applySell(pos: Position, price: number, qty: number): Position {
  const nextQty = pos.qty - qty
  const realized = pos.realized + (sellNet(price, qty) - pos.avg * qty)
  return nextQty <= 0
    ? { qty: 0, avg: 0, realized }
    : { qty: nextQty, avg: pos.avg, realized }
}

/**
 * 평가손익. **모르면 null 을 돌려준다.**
 * 새로고침하면 평단이 사라지므로, 0 으로 채워 틀린 손익을 그리지 않는다.
 * 서버의 held 와 기록된 수량이 어긋나도 모르는 것으로 취급한다.
 */
export function unrealizedFor(
  pos: Position | undefined,
  held: number,
  price: number,
): number | null {
  if (held === 0) return 0
  if (!pos || pos.qty !== held || pos.avg === 0) return null
  return (price - pos.avg) * held
}
