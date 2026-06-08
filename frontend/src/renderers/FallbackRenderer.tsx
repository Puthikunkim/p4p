import type { RendererProps } from './registry'

export function FallbackRenderer({ channel, value }: RendererProps) {
  return (
    <div className="renderer renderer--fallback">
      <div className="renderer__label">
        {channel.display.label}
        <span className="renderer__badge" title={`Unknown hint: ${channel.display.hint}`}>
          ? {channel.display.hint}
        </span>
      </div>
      <div className="renderer__value">
        {value !== undefined ? String(value) : '—'}
      </div>
      <div className="renderer__meta">{channel.unit}</div>
    </div>
  )
}
