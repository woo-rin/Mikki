import { describe, expect, it } from 'vitest'
import { ageAt, publishTick, rampEndTick, rampRemainingAt } from './derive'

describe('경과 시간', () => {
  it('수신 시각을 절대 tick 으로 고정한다', () => {
    // tick 200 에 age_seconds 188 로 받은 기사는 tick 12 에 뜬 것이다
    expect(publishTick(200, 188)).toBe(12)
  })

  it('시간이 흘러도 얼어붙지 않는다', () => {
    const pt = publishTick(200, 188)
    expect(ageAt(200, pt)).toBe(188)
    expect(ageAt(260, pt)).toBe(248)
  })

  it('음수가 되지 않는다', () => {
    expect(ageAt(5, 12)).toBe(0)
  })
})

describe('램프 남은 시간', () => {
  it('수신 시각 기준으로 끝나는 tick 을 고정한다', () => {
    expect(rampEndTick(300, 40)).toBe(340)
  })

  it('이미 반영된 기사는 끝 tick 을 만들지 않는다', () => {
    // ramp_remaining 0 인데 끝 tick 을 만들면 밴드가 진행 중인 것처럼 보인다
    expect(rampEndTick(300, 0)).toBeNull()
  })

  it('남은 시간이 줄어든다', () => {
    const end = rampEndTick(300, 40)
    expect(rampRemainingAt(300, end)).toBe(40)
    expect(rampRemainingAt(320, end)).toBe(20)
  })

  it('끝나면 0 에서 멈춘다', () => {
    const end = rampEndTick(300, 40)
    expect(rampRemainingAt(400, end)).toBe(0)
  })

  it('끝 tick 이 없으면 0 이다', () => {
    expect(rampRemainingAt(300, null)).toBe(0)
  })
})
