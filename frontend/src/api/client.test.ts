import { describe, expect, it } from 'vitest'
import { ApiError, normalize } from './client'

describe('오류 정규화', () => {
  it('detail 아래 중첩된 본문을 그대로 매핑한다', () => {
    const err = normalize(400, {
      detail: { code: 'bad_quantity', message: '수량은 1주 이상이어야 합니다.' },
    })
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
    expect(err.code).toBe('bad_quantity')
    expect(err.message).toBe('수량은 1주 이상이어야 합니다.')
  })

  it('422 는 detail 이 배열이라 모양이 다르다 — 따로 처리한다', () => {
    const err = normalize(422, { detail: [{ loc: ['body', 'qty'], msg: 'not an integer' }] })
    expect(err.code).toBe('bad_request')
    expect(err.message).toBe('요청 형식이 올바르지 않습니다.')
  })

  it('본문 없는 5xx 도 메시지를 갖는다', () => {
    const err = normalize(500, null)
    expect(err.code).toBe('server')
    expect(err.message.length).toBeGreaterThan(0)
  })

  it('세션 소멸을 코드로 알아볼 수 있다', () => {
    const err = normalize(404, {
      detail: { code: 'no_session', message: '세션을 찾을 수 없습니다.' },
    })
    expect(err.code).toBe('no_session')
  })
})
