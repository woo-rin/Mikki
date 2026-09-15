import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { useUiStore } from '../../store/uiStore'
import { Tabs } from './Tabs'

beforeEach(() => {
  useUiStore.setState({ tab: 'news' })
})

describe('탭', () => {
  it('세 탭을 보여주고 현재 탭을 표시한다', () => {
    render(<Tabs />)
    expect(screen.getByRole('tab', { name: '뉴스' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '기업' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: '내 포지션' })).toBeInTheDocument()
  })

  it('누르면 탭이 바뀐다', async () => {
    render(<Tabs />)
    await userEvent.click(screen.getByRole('tab', { name: '기업' }))
    expect(useUiStore.getState().tab).toBe('fundamentals')
  })
})
