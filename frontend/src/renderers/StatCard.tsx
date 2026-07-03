import type { RendererProps } from './registry'

export function StatCard({ channel, value }: RendererProps) {
  const precision = channel.display.precision ?? 2
  // null = channel present but absent this frame ("no data"); undefined = nothing yet.
  const noData = value === null || value === undefined
  const display = noData
    ? value === null ? 'no data' : '—'
    : typeof value === 'number'
      ? value.toFixed(precision)
      : String(value)

  return (
    <div className="renderer renderer--stat-card">
      <div className="renderer__label">{channel.display.label}</div>
      <div className={`renderer__value renderer__value--big${noData ? ' renderer__value--nodata' : ''}`}>{display}</div>
      <div className="renderer__meta">{channel.unit}</div>
    </div>
  )
}
