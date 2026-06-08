import type { RendererProps } from './registry'

export function StatCard({ channel, value }: RendererProps) {
  const precision = channel.display.precision ?? 2
  const display =
    typeof value === 'number'
      ? value.toFixed(precision)
      : value !== undefined
        ? String(value)
        : '—'

  return (
    <div className="renderer renderer--stat-card">
      <div className="renderer__label">{channel.display.label}</div>
      <div className="renderer__value renderer__value--big">{display}</div>
      <div className="renderer__meta">{channel.unit}</div>
    </div>
  )
}
