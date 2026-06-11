import { useVCoreStore } from '../ws/store'

const CHIP_LABELS: Record<string, string> = {
  'om-lsl': 'OM LSL Stream',
  'unity-ws': 'Unity VR Scene',
  'browser-ws': 'Browser WS',
}

function stateLabel(state: string): string {
  const map: Record<string, string> = {
    up: 'Online',
    down: 'Offline',
    connecting: 'Connecting',
    connected: 'Online',
    disconnected: 'Offline',
    stale: 'Stale',
    reconnecting: 'Reconnecting',
  }
  return map[state] ?? state
}

export function SystemConfig() {
  const wsState = useVCoreStore((s) => s.wsState)
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)

  const chips = [
    { key: 'dashboard', name: 'Dashboard WS', state: wsState, detail: null },
    ...Object.entries(linkStatuses).map(([key, ls]) => ({
      key,
      name: CHIP_LABELS[key] ?? key,
      state: ls.state,
      detail: ls.detail ?? null,
    })),
  ]

  return (
    <div className="screen">
      <div style={{ marginBottom: 18 }}>
        <div className="screen-title">System Configuration</div>
        <div className="screen-subtitle">Health check, sensor pipeline status and protocol configuration.</div>
      </div>

      {/* Status chips row */}
      <div className="status-chips-row" style={{ gridTemplateColumns: `repeat(${Math.min(chips.length, 4)}, 1fr)` }}>
        {chips.map((chip) => (
          <div key={chip.key} className="status-chip">
            <span className="status-chip__name">{chip.name}</span>
            <div className="status-chip__value-row">
              <span className="status-chip__value">{stateLabel(chip.state)}</span>
              <span className={`status-dot status-dot--${chip.state}`} />
            </div>
            {chip.detail && (
              <span style={{ fontSize: 11, opacity: 0.55 }}>{chip.detail}</span>
            )}
          </div>
        ))}
      </div>

      {/* Connection section */}
      <section className="config-section">
        <div className="config-section-header">
          <span className="config-section-title">Connection Details</span>
        </div>
        <table className="config-table">
          <tbody>
            {chips.map((chip) => (
              <tr key={chip.key}>
                <td>{chip.name}</td>
                <td>
                  <span className={`badge badge--${chip.state}`}>{chip.state}</span>
                  {chip.detail && <span className="config-meta">{chip.detail}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Configuration section */}
      <section className="config-section">
        <div className="config-section-header">
          <span className="config-section-title">Configuration</span>
        </div>
        <p className="empty-state">
          Edit <code>backend/config.yaml</code> to configure LSL stream names,
          WS bind address, and ZMQ endpoints.
        </p>
      </section>
    </div>
  )
}
