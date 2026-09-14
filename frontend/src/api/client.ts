export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/**
 * FastAPI 의 HTTPException 은 본문을 detail 아래 중첩한다.
 * 자료형이 틀린 요청만 422 와 함께 detail 이 배열인 다른 모양으로 온다.
 */
export function normalize(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { code?: unknown; message?: unknown }
    if (typeof d.code === 'string' && typeof d.message === 'string') {
      return new ApiError(status, d.code, d.message)
    }
  }
  if (status === 422) {
    return new ApiError(422, 'bad_request', '요청 형식이 올바르지 않습니다.')
  }
  return new ApiError(status, 'server', '서버에서 오류가 발생했습니다.')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'network', '서버에 연결할 수 없습니다.')
  }
  if (res.ok) return (await res.json()) as T

  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // 본문이 없거나 JSON 이 아니다. normalize 가 상태코드만으로 처리한다.
  }
  throw normalize(res.status, body)
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
