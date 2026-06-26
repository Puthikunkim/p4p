import type { RendererProps } from './registry'

// Affective-state cells (active cell keeps white text, so each colour is a mid-saturation
// hue that stays legible on the dark card). Distinct from the brand lime, which is too light
// to carry white text.
const QUADRANT_COLORS: Record<string, string> = {
  calm: '#12b886',     // teal-green
  engaged: '#6366f1',  // indigo
  stressed: '#ef4444', // red
  bored: '#64748b',    // slate
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
            style={current === cat ? { background: QUADRANT_COLORS[cat] ?? '#475569' } : {}}
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
