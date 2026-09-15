import { describe, expect, it } from 'vitest'
import { eok, pct, signedWon, won } from './format'

describe('원 표기', () => {
  it('천 단위를 끊는다', () => {
    expect(won(1_500_000)).toBe('1,500,000원')
  })

  it('손익은 부호를 붙이고, 모르면 — 다', () => {
    expect(signedWon(1200)).toBe('+1,200원')
    expect(signedWon(-1200)).toBe('-1,200원')
    expect(signedWon(null)).toBe('—')
  })
})

describe('퍼센트', () => {
  it('양수에만 + 를 붙이고 소수 둘째 자리까지 쓴다', () => {
    expect(pct(7.071)).toBe('+7.07%')
    expect(pct(-7.07)).toBe('-7.07%')
  })
})

describe('억 표기', () => {
  it('재무 숫자는 억 단위로 줄인다', () => {
    expect(eok(81_200_000_000)).toBe('812억')
    expect(eok(16_500_000_000)).toBe('165억')
  })

  it('적자는 음수로 그대로 쓴다', () => {
    expect(eok(-2_400_000_000)).toBe('-24억')
  })

  it('억 미만은 0 으로 뭉개지 않고 소수로 쓴다', () => {
    expect(eok(45_000_000)).toBe('0.5억')
  })
})
