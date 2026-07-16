import type { RendererProps } from './registry'

// Affective-state cell colours. Keyed by BOTH the sensor-pipeline emotion labels
// (valence/arousal circumplex) and the legacy affect labels used by the mock
// pipeline + session fixtures, so both quadrants stay coloured. The active cell
// keeps white text, so each colour is a mid-saturation hue that stays legible on
// the dark card. Distinct from the brand lime, which is too light to carry white.
const QUADRANT_COLORS: Record<string, string> = {
  // valence / arousal circumplex (Contract 1 emotion channel)
  'Positive / High arousal': '#6366f1', // excited/engaged — indigo
  'Negative / High arousal': '#ef4444', // stressed — red
  'Negative / Low arousal': '#64748b',  // bored — slate
  'Positive / Low arousal': '#12b886',  // calm/content — teal-green
  // legacy affect labels (mock pipeline + session fixtures)
  calm: '#12b886',
  engaged: '#6366f1',
  stressed: '#ef4444',
  bored: '#64748b',
}

// Lay the valence/arousal circumplex on its conventional axes: valence horizontal
// (negative left, positive right), arousal vertical (high top, low bottom). Returns
// the four categories in row-major grid order (TL, TR, BL, BR) when they parse
// cleanly as a circumplex, else null so the caller falls back to declared order.
function circumplexOrder(categories: string[]): string[] | null {
  if (categories.length !== 4) return null
  const slots: (string | null)[] = [null, null, null, null]
  for (const cat of categories) {
    const lc = cat.toLowerCase()
    const col = lc.includes('positive') ? 1 : lc.includes('negative') ? 0 : -1
    const row = lc.includes('high') ? 0 : lc.includes('low') ? 1 : -1
    if (col === -1 || row === -1) return null
    const slot = row * 2 + col
    if (slots[slot] !== null) return null // duplicate quadrant → not a clean circumplex
    slots[slot] = cat
  }
  return slots.every((s) => s !== null) ? (slots as string[]) : null
}

export function Quadrant({ channel, value }: RendererProps) {
  const categories: string[] = channel.categories ?? []
  const current = typeof value === 'string' ? value : undefined
  const cells = circumplexOrder(categories) ?? categories

  return (
    <div className="renderer renderer--quadrant">
      <div className="renderer__label">{channel.display.label}</div>
      <div className="renderer__quadrant-grid">
        {cells.map((cat) => (
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
