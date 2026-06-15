import type { RendererProps } from './registry'

const QUADRANT_COLORS: Record<string, string> = {
  calm: '#0e9f6e',
  engaged: '#4338ca',
  stressed: '#d4322a',
  bored: '#8b94a4',
}

export function Quadrant({ channel, value }: RendererProps) {
  const categories = channel.categories ?? []
  const current = typeof value === 'string' ? value : undefined

  return (
    <div className="renderer renderer--quadrant">
      <div className="renderer__label">{channel.display.label}</div>
      <div className="renderer__quadrant-grid">
        {categories.map((cat) => (
          <div
            key={cat}
            className={`renderer__quadrant-cell ${current === cat ? 'renderer__quadrant-cell--active' : ''}`}
            style={current === cat ? { background: QUADRANT_COLORS[cat] ?? '#475063' } : {}}
          >
            {cat}
          </div>
        ))}
      </div>
      {categories.length === 0 && (
        <div className="renderer__value">{value !== undefined ? String(value) : '—'}</div>
      )}
    </div>
  )
}
