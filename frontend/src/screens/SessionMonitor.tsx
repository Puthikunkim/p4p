import { useVCoreStore, useChannels } from '../ws/store'
import { getRenderer } from '../renderers/registry'
import { VideoFeed } from '../video/VideoFeed'

export function SessionMonitor() {
  const channels = useChannels()
  const latestValues = useVCoreStore((s) => s.latestValues)
  const history = useVCoreStore((s) => s.history)
  const warnings = useVCoreStore((s) => s.warnings)
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)
  const clearWarnings = useVCoreStore((s) => s.clearWarnings)
  const rules = useVCoreStore((s) => s.rules)
  const disabledRules = useVCoreStore((s) => s.disabledRules)
  const activeSessionId = useVCoreStore((s) => s.activeSessionId)

  return (
    <div className="screen">
      <h2>Session Monitor</h2>

      {/* Link status strip */}
      <div className="link-strip">
        {(['om-lsl', 'unity-ws', 'browser-ws'] as const).map((link) => {
          const ls = linkStatuses[link]
          return (
            <div key={link} className={`link-chip link-chip--${ls?.state ?? 'down'}`}>
              {link}: {ls?.state ?? 'down'}
            </div>
          )
        })}
      </div>

      {/* Video mirror */}
      <VideoFeed sessionId={activeSessionId} />

      {/* Channel renderers — driven entirely by the manifest, no code change needed */}
      {channels.length === 0 ? (
        <p className="empty-state">Waiting for signal manifest…</p>
      ) : (
        <div className="renderer-grid">
          {channels.map((ch) => {
            const Renderer = getRenderer(ch)
            return (
              <Renderer
                key={ch.name}
                channel={ch}
                value={latestValues[ch.name]}
                history={history[ch.name] ?? []}
              />
            )
          })}
        </div>
      )}

      {/* Rule status */}
      {rules.length > 0 && (
        <section className="rule-status-section">
          <h3>Active Rules</h3>
          <div className="rule-status-list">
            {rules.map((r) => {
              const reason = disabledRules[r.id]
              return (
                <div key={r.id} className={`rule-status-item ${reason ? 'rule-status-item--disabled' : 'rule-status-item--active'}`}>
                  <span className="rule-status-id">{r.id}</span>
                  {reason && <span className="rule-status-reason"> — {reason}</span>}
                  {!reason && (
                    <button
                      className="btn btn--small"
                      onClick={() => triggerRule(r.id)}
                    >
                      Activate
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <section className="warnings-section">
          <div className="warnings-header">
            <h3>Warnings ({warnings.length})</h3>
            <button className="btn btn--small btn--ghost" onClick={clearWarnings}>Clear</button>
          </div>
          <ul className="warnings-list">
            {warnings.map((w, i) => (
              <li key={i} className="warning-item">
                <span className="warning-source">{w.source}</span>: {w.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

async function triggerRule(ruleId: string): Promise<void> {
  const resp = await fetch(`/api/rules/${encodeURIComponent(ruleId)}/trigger`, { method: 'POST' })
  if (!resp.ok) {
    const body = await resp.json() as { detail?: string }
    console.warn('trigger failed:', body.detail ?? resp.status)
  }
}
