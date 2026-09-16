import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { BoardPost } from '../../api/types'
import { useDerivedStore } from '../../store/derivedStore'
import { BoardFeed } from './BoardFeed'

function post(postId: number, patch: Partial<BoardPost> = {}): BoardPost {
  return {
    post_id: postId, news_id: 1, author: '김부장', symbol: 'geno',
    name: '제노셀', body: '이거 진짜 간다', age_seconds: 12, offline: false, ...patch,
  }
}

beforeEach(() => useDerivedStore.getState().reset())

describe('종토방', () => {
  it('아직 글이 없으면 그렇게 말한다', () => {
    render(<BoardFeed />)
    expect(screen.getByText(/아직 조용합니다/)).toBeInTheDocument()
  })

  it('작성자·종목·본문을 보여준다', () => {
    useDerivedStore.setState({ posts: [post(1)] })
    render(<BoardFeed />)
    expect(screen.getByText('김부장')).toBeInTheDocument()
    expect(screen.getByText('제노셀')).toBeInTheDocument()
    expect(screen.getByText('이거 진짜 간다')).toBeInTheDocument()
  })

  it('최신 글이 위에 온다', () => {
    useDerivedStore.setState({
      posts: [post(2, { author: '박선배' }), post(1, { author: '정소장' })],
    })
    render(<BoardFeed />)
    const authors = screen.getAllByTestId('post-author').map((e) => e.textContent)
    expect(authors).toEqual(['박선배', '정소장'])
  })

  it('강세·약세를 색으로 구분하지 않는다 — 문장으로만 읽어야 한다', () => {
    useDerivedStore.setState({ posts: [post(1)] })
    const { container } = render(<BoardFeed />)
    expect(container.querySelector('.up, .down')).toBeNull()
  })

  it('로컬 템플릿이면 배지를 단다', () => {
    useDerivedStore.setState({ posts: [post(1, { offline: true })] })
    render(<BoardFeed />)
    expect(screen.getByText('로컬')).toBeInTheDocument()
  })
})
