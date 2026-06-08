import { describe, it, expect, beforeEach } from 'vitest'
import { registerRenderer, registerFallback, getRenderer } from './registry'
import type { Channel } from '../contracts/SignalSchema'
import type { ComponentType } from 'react'
import type { RendererProps } from './registry'

function makeChannel(overrides: Partial<Channel> & { name?: string } = {}): Channel {
  return {
    name: overrides.name ?? 'ch',
    unit: 'normalized',
    type: overrides.type ?? 'scalar',
    display: { hint: overrides.display?.hint ?? 'unknown_hint', label: 'Label', ...overrides.display },
    ...overrides,
  } as Channel
}

const Dummy: ComponentType<RendererProps> = () => null

beforeEach(() => {
  // re-register known hints before each test
  registerFallback(Dummy)
  registerRenderer('stat_card', Dummy)
  registerRenderer('line_chart', Dummy)
  registerRenderer('quadrant', Dummy)
})

describe('getRenderer', () => {
  it('returns component registered for the exact hint', () => {
    const CustomComp: ComponentType<RendererProps> = () => null
    registerRenderer('my_hint', CustomComp)
    const ch = makeChannel({ display: { hint: 'my_hint', label: 'L' } })
    expect(getRenderer(ch)).toBe(CustomComp)
  })

  it('falls back to type-based hint for scalar', () => {
    const ch = makeChannel({ type: 'scalar', display: { hint: 'no_such_hint', label: 'L' } })
    expect(getRenderer(ch)).toBe(Dummy)  // stat_card registered as Dummy
  })

  it('falls back to type-based hint for timeseries', () => {
    const ch = makeChannel({ type: 'timeseries', display: { hint: 'no_such_hint', label: 'L' } })
    expect(getRenderer(ch)).toBe(Dummy)  // line_chart registered as Dummy
  })

  it('falls back to type-based hint for categorical', () => {
    const ch = makeChannel({ type: 'categorical', display: { hint: 'no_such_hint', label: 'L' } })
    expect(getRenderer(ch)).toBe(Dummy)  // quadrant registered as Dummy
  })

  it('returns fallback when hint and type-map both miss', () => {
    const ch = makeChannel({ type: 'scalar' as any, display: { hint: 'absolute_unknown', label: 'L' } })
    // Clear stat_card to force full fallback
    registerRenderer('stat_card', undefined as any)
    expect(getRenderer(ch)).toBe(Dummy)  // __fallback__
  })
})
