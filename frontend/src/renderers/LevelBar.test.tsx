import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { LevelBar } from './LevelBar'
import type { Channel } from '../contracts/SignalSchema'

afterEach(cleanup)

const channel: Channel = {
  name: 'cognitive_load',
  unit: 'class',
  type: 'categorical',
  categories: ['Low', 'Medium', 'High'],
  display: { hint: 'level_bar', label: 'Cognitive Load' },
}

function segments(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('.renderer__level-seg'))
}

// A segment is "filled" when it carries an inline background (the ramp colour);
// unfilled segments have no inline style.
function filledCount(container: HTMLElement): number {
  return segments(container).filter((s) => s.style.background !== '').length
}

describe('LevelBar', () => {
  it('renders one segment per category', () => {
    const { container } = render(<LevelBar channel={channel} value="Low" history={[]} />)
    expect(segments(container)).toHaveLength(3)
  })

  it('fills segments up to and including the current level', () => {
    const low = render(<LevelBar channel={channel} value="Low" history={[]} />)
    expect(filledCount(low.container)).toBe(1)
    cleanup()

    const mid = render(<LevelBar channel={channel} value="Medium" history={[]} />)
    expect(filledCount(mid.container)).toBe(2)
    cleanup()

    const high = render(<LevelBar channel={channel} value="High" history={[]} />)
    expect(filledCount(high.container)).toBe(3)
  })

  it('shows the current category as the caption', () => {
    const { getByText } = render(<LevelBar channel={channel} value="Medium" history={[]} />)
    expect(getByText('Medium')).toBeTruthy()
  })

  it('fills nothing and shows "no data" when the channel is present but absent this frame', () => {
    const { container, getByText } = render(<LevelBar channel={channel} value={null} history={[]} />)
    expect(filledCount(container)).toBe(0)
    expect(getByText('no data')).toBeTruthy()
  })

  it('fills nothing and shows an em-dash before the first sample', () => {
    const { container, getByText } = render(<LevelBar channel={channel} value={undefined} history={[]} />)
    expect(filledCount(container)).toBe(0)
    expect(getByText('—')).toBeTruthy()
  })

  it('fills nothing when the value is not a known category', () => {
    const { container } = render(<LevelBar channel={channel} value="Unknown" history={[]} />)
    expect(filledCount(container)).toBe(0)
  })
})
