import { describe, expect, it } from 'vitest'
import { buyCost, fee, maxBuyQty, sellNet, unrealized } from './money'

describe('수수료', () => {
  it('0.2% 를 내림한다', () => {
    // 44618 * 2 = 89236, * 0.002 = 178.472 → 178. api.md §3 실제 캡처와 같다
    expect(fee(44618, 2)).toBe(178)
  })

  it('1원 미만이면 0 이다', () => {
    expect(fee(100, 1)).toBe(0)
  })

  it('매수는 더하고 매도는 뺀다', () => {
    expect(buyCost(44618, 2)).toBe(89236 + 178)
    expect(sellNet(44618, 2)).toBe(89236 - 178)
  })
})

describe('최대 매수 수량', () => {
  it('경계에서 정확하다 — q 는 사지고 q+1 은 못 산다', () => {
    const cash = 1_000_000
    const price = 82_000
    const q = maxBuyQty(cash, price)
    expect(buyCost(price, q)).toBeLessThanOrEqual(cash)
    expect(buyCost(price, q + 1)).toBeGreaterThan(cash)
  })

  it('현금이 한 주 값도 안 되면 0 이다', () => {
    expect(maxBuyQty(1000, 82_000)).toBe(0)
  })

  it('수수료 때문에 단순 나눗셈보다 작을 수 있다', () => {
    // 현금 100000, 가격 10000 → 나눗셈은 10 주지만 수수료 200 원이 모자란다
    expect(maxBuyQty(100_000, 10_000)).toBe(9)
  })

  it('여러 가격대에서 불변식을 지킨다', () => {
    for (const price of [18_500, 24_000, 33_000, 45_000, 61_000, 82_000]) {
      for (const cash of [99_999, 1_000_000, 3_333_333]) {
        const q = maxBuyQty(cash, price)
        expect(buyCost(price, q)).toBeLessThanOrEqual(cash)
        expect(buyCost(price, q + 1)).toBeGreaterThan(cash)
      }
    }
  })
})

describe('평가손익', () => {
  it('보유가 없으면 0 이다', () => {
    expect(unrealized(null, 50_000, 0)).toBe(0)
  })

  it('평단을 모르면 null 이다 — 0 으로 채워 틀린 손익을 그리지 않는다', () => {
    expect(unrealized(null, 50_000, 3)).toBeNull()
  })

  it('맞으면 (현재가 - 평단) × 수량 이다', () => {
    expect(unrealized(45_090, 50_000, 3)).toBe((50_000 - 45_090) * 3)
  })

  it('손실이면 음수다', () => {
    expect(unrealized(50_000, 45_000, 2)).toBe(-10_000)
  })
})
