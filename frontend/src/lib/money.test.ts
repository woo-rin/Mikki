import { describe, expect, it } from 'vitest'
import {
  applyBuy, applySell, buyCost, emptyPosition, fee,
  maxBuyQty, sellNet, unrealizedFor,
} from './money'

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

describe('평단', () => {
  it('매수 수수료를 포함해 내림한다', () => {
    const pos = applyBuy(emptyPosition(), 10_000, 3)
    // buyCost = 30000 + 60 = 30060, / 3 = 10020
    expect(pos).toEqual({ qty: 3, avg: 10_020, realized: 0 })
  })

  it('두 번 사면 가중평균이 된다', () => {
    let pos = applyBuy(emptyPosition(), 10_000, 1) // 10020
    pos = applyBuy(pos, 20_000, 1)                 // +40
    // (10020 + 20040) / 2 = 15030
    expect(pos.qty).toBe(2)
    expect(pos.avg).toBe(15_030)
  })

  it('일부 매도는 평단을 유지하고 수량만 줄인다', () => {
    const bought = applyBuy(emptyPosition(), 10_000, 3)
    const sold = applySell(bought, 12_000, 1)
    expect(sold.qty).toBe(2)
    expect(sold.avg).toBe(bought.avg)
  })

  it('전량 매도 후 평단이 0 으로 리셋되고 실현손익이 남는다', () => {
    const bought = applyBuy(emptyPosition(), 10_000, 2) // avg 10020
    const sold = applySell(bought, 12_000, 2)
    // sellNet = 24000 - 48 = 23952, 원가 10020*2 = 20040
    expect(sold).toEqual({ qty: 0, avg: 0, realized: 23_952 - 20_040 })
  })
})

describe('평가손익', () => {
  it('보유가 없으면 0 이다', () => {
    expect(unrealizedFor(undefined, 0, 50_000)).toBe(0)
  })

  it('평단을 모르면 null 이다 — 새로고침 후 상태', () => {
    expect(unrealizedFor(undefined, 3, 50_000)).toBeNull()
  })

  it('보유 수량과 기록이 어긋나도 null 이다', () => {
    const pos = applyBuy(emptyPosition(), 10_000, 3)
    expect(unrealizedFor(pos, 5, 50_000)).toBeNull()
  })

  it('맞으면 (현재가 - 평단) × 수량 이다', () => {
    const pos = applyBuy(emptyPosition(), 10_000, 3) // avg 10020
    expect(unrealizedFor(pos, 3, 12_000)).toBe((12_000 - 10_020) * 3)
  })
})
