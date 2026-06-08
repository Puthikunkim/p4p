import type { RendererProps } from './registry'

const QUADRANT_COLORS: Record<string, string> = {
  calm: '#4caf50',
  engaged: '#2196f3',
  stressed: '#f44336',
  bored: '#9e9e9e',
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
            style={current === cat ? { background: QUADRANT_COLORS[cat] ?? '#607d8b' } : {}}
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
