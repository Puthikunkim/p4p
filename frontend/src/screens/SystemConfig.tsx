import { useVCoreStore } from '../ws/store'
import { LINK_ORDER, linkLabel } from '../ws/links'

function stateLabel(state: string): string {
  const map: Record<string, string> = {
    up: 'Online',
    down: 'Offline',
    stale: 'Stale',
    reconnecting: 'Reconnecting',
    unknown: 'Unknown',
  }
  return map[state] ?? state
}

export function SystemConfig() {
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)

  // Render the canonical links (Sensor Pipeline, Unity WS, Browser WS) in a stable order,
  // defaulting any not-yet-reported link to "down" — same as SessionMonitor's link strip,
  // so every page shows the same three indicators rather than only those already received.
  const chips = LINK_ORDER.map((key) => ({
    key,
    name: linkLabel(key),
    state: linkStatuses[key]?.state ?? 'down',
  }))

  return (
    <div className="screen">
      <div style={{ marginBottom: 18 }}>
        <div className="screen-title">System Configuration</div>
      </div>

      <div className="status-chips-row" style={{ gridTemplateColumns: `repeat(${Math.min(chips.length, 4)}, 1fr)` }}>
        {chips.map((chip) => (
          <div key={chip.key} className="status-chip">
            <span className="status-chip__name">{chip.name}</span>
            <div className="status-chip__value-row">
              <span className="status-chip__value">{stateLabel(chip.state)}</span>
              <span className={`status-dot status-dot--${chip.state}`} />
            </div>
          </div>
        ))}
      </div>

      <section className="config-section">
        <div className="config-section-header">
          <span className="config-section-title">Configuration</span>
        </div>
        <p className="empty-state">
          Edit <code>backend/config.yaml</code> to configure LSL stream names,
          the WS bind address, recording paths, and LiveKit settings.
        </p>
      </section>
    </div>
  )
}
