import { useVCoreStore } from '../ws/store'

const CHIP_LABELS: Record<string, string> = {
  'browser-ws': 'Browser WS',
  'unity-ws': 'Unity VR Scene',
  'om-lsl': 'OM LSL Stream',
}

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

const PIPELINE_STAGES = [
  { key: 'browser-ws', label: 'Browser → Backend' },
  { key: 'om-lsl', label: 'OM LSL → Backend' },
  { key: 'unity-ws', label: 'Backend → Unity' },
]

function derivePipelineState(browserWsState: string | undefined, omLslState: string | undefined): string {
  if (!browserWsState || browserWsState === 'down') return 'down'
  if (browserWsState !== 'up') return browserWsState
  if (!omLslState) return 'unknown'
  return omLslState
}

export function SystemConfig() {
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)

  const browserWsState = linkStatuses['browser-ws']?.state
  const omLslState = linkStatuses['om-lsl']?.state
  const pipelineState = derivePipelineState(browserWsState, omLslState)

  const pipelineStages = PIPELINE_STAGES.map((stage) => {
    const ls = linkStatuses[stage.key]
    return { ...stage, state: ls?.state ?? 'unknown', detail: ls?.detail ?? null }
  })

  const chips = Object.entries(linkStatuses).map(([key, ls]) => ({
    key,
    name: CHIP_LABELS[key] ?? key,
    state: ls.state,
    detail: ls.detail ?? null,
  }))

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

      {/* Signal pipeline section */}
      <section className="config-section">
        <div className="config-section-header">
          <span className="config-section-title">Signal Pipeline</span>
          <span className={`badge badge--${pipelineState}`} style={{ marginLeft: 10 }}>
            {stateLabel(pipelineState)}
          </span>
        </div>
        <table className="config-table">
          <tbody>
            {pipelineStages.map((stage) => (
              <tr key={stage.key}>
                <td>{stage.label}</td>
                <td>
                  <span className={`badge badge--${stage.state}`}>{stateLabel(stage.state)}</span>
                  {stage.detail && <span className="config-meta">{stage.detail}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

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
