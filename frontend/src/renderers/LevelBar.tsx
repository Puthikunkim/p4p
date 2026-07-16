import type { RendererProps } from './registry'

// Ordinal severity ramp: teal (low) → amber (mid) → red (high). Piecewise-linear
// in hue so a 3-level scale lands on teal/amber/red exactly and longer scales
// interpolate smoothly. Saturation/lightness tuned to stay legible on the dark card.
function rampColor(position: number): string {
  const p = Math.max(0, Math.min(1, position))
  const hue = p <= 0.5 ? 158 + (40 - 158) * (p / 0.5) : 40 + (0 - 40) * ((p - 0.5) / 0.5)
  return `hsl(${Math.round(hue)}, 62%, 46%)`
}

// Segmented level meter for ordinal categoricals (e.g. Low < Medium < High).
// Categories are ordered low→high; segments up to and including the current level
// are filled with the rising severity ramp so both the level and its severity read
// at a glance. Distinct from Quadrant, which encodes an unordered 2×2 affect grid.
export function LevelBar({ channel, value }: RendererProps) {
  const categories: string[] = channel.categories ?? []
  // null = channel present but absent this frame ("no data"); undefined = nothing yet.
  const noData = value === null || value === undefined
  const current = typeof value === 'string' ? value : undefined
  const currentIdx = current ? categories.indexOf(current) : -1
  const caption = noData ? (value === null ? 'no data' : '—') : current ?? String(value)

  if (categories.length === 0) {
    return (
      <div className="renderer renderer--level-bar">
        <div className="renderer__label">{channel.display.label}</div>
        <div className={`renderer__value${noData ? ' renderer__value--nodata' : ''}`}>{caption}</div>
      </div>
    )
  }

  return (
    <div className="renderer renderer--level-bar">
      <div className="renderer__label">{channel.display.label}</div>
      <div className="renderer__level-bar">
        {categories.map((cat, i) => {
          const filled = currentIdx >= 0 && i <= currentIdx
          const pos = categories.length > 1 ? i / (categories.length - 1) : 0
          return (
            <div
              key={cat}
              className={`renderer__level-seg${filled ? ' renderer__level-seg--filled' : ''}`}
              style={filled ? { background: rampColor(pos) } : {}}
              title={cat}
            />
          )
        })}
      </div>
      <div className={`renderer__level-caption${noData ? ' renderer__value--nodata' : ''}`}>{caption}</div>
    </div>
  )
}
