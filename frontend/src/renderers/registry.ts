import type { ComponentType } from 'react'
import type { Channel } from '../contracts/SignalSchema'

export interface RendererProps {
  channel: Channel
  value: number | string | undefined
  history: [number, number][]  // [lsl_timestamp, numeric_value]
}

type RendererComponent = ComponentType<RendererProps>

// Registry maps display.hint → component.
// Unknown hints fall through to FallbackRenderer.
const registry = new Map<string, RendererComponent>()

export function registerRenderer(hint: string, component: RendererComponent): void {
  registry.set(hint, component)
}

export function getRenderer(channel: Channel): RendererComponent {
  const byHint = registry.get(channel.display.hint)
  if (byHint) return byHint

  // Secondary fallback: map channel type → common hint
  const byType: Record<string, string> = {
    scalar: 'stat_card',
    timeseries: 'line_chart',
    categorical: 'quadrant',
  }
  const fallbackHint = byType[channel.type]
  if (fallbackHint) {
    const byTypedHint = registry.get(fallbackHint)
    if (byTypedHint) return byTypedHint
  }

  // Last resort: FallbackRenderer (registered lazily by the root)
  return registry.get('__fallback__')!
}

export function registerFallback(component: RendererComponent): void {
  registry.set('__fallback__', component)
}
