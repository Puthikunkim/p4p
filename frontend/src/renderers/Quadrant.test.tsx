import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { Quadrant } from './Quadrant'
import type { Channel } from '../contracts/SignalSchema'

afterEach(cleanup)

function channel(categories: string[], name = 'emotion', label = 'Emotion'): Channel {
  return {
    name,
    unit: 'class',
    type: 'categorical',
    categories: categories as [string, ...string[]],
    display: { hint: 'quadrant', label },
  }
}

const EMOTION_CATS = [
  'Positive / High arousal',
  'Negative / High arousal',
  'Negative / Low arousal',
  'Positive / Low arousal',
]

function cells(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('.renderer__quadrant-cell'))
}

function activeCell(container: HTMLElement): HTMLElement | undefined {
  return cells(container).find((c) => c.classList.contains('renderer__quadrant-cell--active'))
}

describe('Quadrant', () => {
  it('lays emotion labels on circumplex axes: valence x (neg left, pos right), arousal y (high top)', () => {
    // The wire/category order is [Pos/High, Neg/High, Neg/Low, Pos/Low]; the grid must
    // render them row-major as TL, TR, BL, BR of the conventional circumplex.
    const { container } = render(<Quadrant channel={channel(EMOTION_CATS)} value={undefined} history={[]} />)
    expect(cells(container).map((c) => c.textContent)).toEqual([
      'Negative / High arousal', // TL
      'Positive / High arousal', // TR
      'Negative / Low arousal', // BL
      'Positive / Low arousal', // BR
    ])
  })

  it('applies the mapped colour to a known active label, distinct from the grey fallback', () => {
    const known = render(<Quadrant channel={channel(EMOTION_CATS)} value="Positive / Low arousal" history={[]} />)
    const knownBg = activeCell(known.container)!.style.background
    cleanup()

    const unknown = render(<Quadrant channel={channel(['aaa', 'bbb'], 'x', 'X')} value="aaa" history={[]} />)
    const unknownBg = activeCell(unknown.container)!.style.background

    expect(knownBg).not.toBe('') // a colour is applied
    expect(knownBg).not.toBe(unknownBg) // mapped teal vs the grey fallback
  })

  it('keeps declared order and still colours the active cell for legacy affect labels', () => {
    const affect = ['calm', 'stressed', 'bored', 'engaged']
    const { container } = render(
      <Quadrant channel={channel(affect, 'affect', 'Affective State')} value="calm" history={[]} />,
    )
    // Not a valence/arousal circumplex → declared order preserved.
    expect(cells(container).map((c) => c.textContent)).toEqual(affect)
    expect(activeCell(container)?.style.background).not.toBe('')
  })

  it('falls back to declared order when categories are not a clean circumplex', () => {
    const cats = ['Positive / High arousal', 'Negative / High arousal', 'Neutral', 'Positive / Low arousal']
    const { container } = render(<Quadrant channel={channel(cats)} value={undefined} history={[]} />)
    expect(cells(container).map((c) => c.textContent)).toEqual(cats)
  })
})
