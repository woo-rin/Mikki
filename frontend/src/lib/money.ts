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

/**
 * 평가손익. 평단은 서버가 avg_cost 로 준다 — 안 들고 있으면 null 이다.
 * null 을 0 으로 바꾸지 않는다. 그러면 틀린 손익이 그럴듯하게 그려진다.
 */
export function unrealized(
  avgCost: number | null,
  price: number,
  held: number,
): number | null {
  if (held === 0) return 0
  if (avgCost === null) return null
  return (price - avgCost) * held
}
