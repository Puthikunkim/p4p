import { useVCoreStore, useChannels } from '../ws/store'
import { getRenderer } from '../renderers/registry'
import { VideoFeed } from '../video/VideoFeed'
import type { Channel } from '../contracts/SignalSchema'

const GROUP_LABELS: Record<string, string> = {
  physiological: 'Physiological',
  behavioural: 'Behavioural Markers',
  vr_context: 'VR Context',
}

const GROUP_ORDER = ['physiological', 'behavioural', 'vr_context']

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

  // Partition channels into groups
  const grouped = new Map<string, Channel[]>()
  const ungrouped: Channel[] = []
  for (const ch of channels) {
    const g = (ch.display as Record<string, unknown>).group as string | undefined
    if (g) {
      if (!grouped.has(g)) grouped.set(g, [])
      grouped.get(g)!.push(ch)
    } else {
      ungrouped.push(ch)
    }
  }
  const hasGroups = grouped.size > 0

  return (
    <div className="screen">
      {/* Link status strip */}
      <div className="link-strip">
        {(['om-lsl', 'unity-ws', 'browser-ws'] as const).map((link) => {
          const ls = linkStatuses[link]
          const state = ls?.state ?? 'down'
          return (
            <div key={link} className={`link-chip link-chip--${state}`}>
              <span className={`status-dot status-dot--${state}`} />
              {link}
            </div>
          )
        })}
      </div>

      <div className="monitor-layout">
        {/* Left: main content */}
        <div className="monitor-main">
          <VideoFeed sessionId={activeSessionId} />

          {channels.length === 0 ? (
            <p className="empty-state">Waiting for signal manifest…</p>
          ) : hasGroups ? (
            <>
              <div className="signal-panels">
                {GROUP_ORDER.filter((g) => grouped.has(g)).map((g) => (
                  <SignalPanel
                    key={g}
                    groupKey={g}
                    channels={grouped.get(g)!}
                    latestValues={latestValues}
                    history={history}
                  />
                ))}
                {/* any extra groups not in GROUP_ORDER */}
                {[...grouped.keys()]
                  .filter((g) => !GROUP_ORDER.includes(g))
                  .map((g) => (
                    <SignalPanel
                      key={g}
                      groupKey={g}
                      channels={grouped.get(g)!}
                      latestValues={latestValues}
                      history={history}
                    />
                  ))}
              </div>
              {ungrouped.length > 0 && (
                <div className="renderer-grid">
                  {ungrouped.map((ch) => {
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
            </>
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

        {/* Right: Available Rules panel */}
        <div className="monitor-sidebar">
          <div className="rules-panel">
            <div className="rules-panel__header">
              <div className="rules-panel__title">Available Rules</div>
              <div className="rules-panel__subtitle">Click to fire a manual override</div>
            </div>

            <div className="rules-panel__list">
              {rules.length === 0 ? (
                <p className="empty-state" style={{ padding: '8px 4px', fontSize: 12 }}>
                  No rules loaded.
                </p>
              ) : (
                rules.map((r) => {
                  const disabled = !!disabledRules[r.id]
                  const cond = 'all' in r.when ? r.when.all[0] : r.when.any[0]
                  const action = r.then?.set
                  return (
                    <button
                      key={r.id}
                      className="rule-btn"
                      onClick={() => triggerRule(r.id)}
                      disabled={disabled}
                      title={disabled ? `Disabled: ${disabledRules[r.id]}` : 'Click to fire manually'}
                    >
                      <span className="rule-btn__name">
                        {r.description || r.id}
                      </span>
                      <div className="rule-btn__meta">
                        {cond && (
                          <span className="rule-btn__chip">
                            {cond.signal} {cond.op} {cond.threshold ?? cond.value}
                          </span>
                        )}
                        {action && (
                          <span className="rule-btn__chip" style={{ opacity: 0.75 }}>
                            {action.status}={String(action.value)}
                          </span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Adaptation Log */}
          <div className="adapt-log">
            <div className="adapt-log__header">
              <span>Adaptation Log</span>
              {warnings.length > 0 && (
                <button className="btn btn--small btn--ghost" style={{ padding: '2px 8px', fontSize: 11 }} onClick={clearWarnings}>
                  Clear
                </button>
              )}
            </div>
            <div className="adapt-log__list">
              {warnings.length === 0 ? (
                <div className="adapt-log__empty">No events yet — fire a rule to see it here.</div>
              ) : (
                warnings.slice(0, 20).map((w, i) => (
                  <div key={i} className="adapt-log__entry">
                    <span className="adapt-log__time">
                      {new Date(w.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                    <div>
                      <span className="adapt-log__source">{w.source}</span>
                      <span className="adapt-log__msg"> — {w.message}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

interface SignalPanelProps {
  groupKey: string
  channels: Channel[]
  latestValues: Record<string, number | string>
  history: Record<string, [number, number][]>
}

function SignalPanel({ groupKey, channels, latestValues, history }: SignalPanelProps) {
  const label = GROUP_LABELS[groupKey] ?? groupKey.replace(/_/g, ' ').toUpperCase()
  const isVrContext = groupKey === 'vr_context'

  return (
    <div className="signal-panel">
      <div className="signal-panel__header">
        <span className="signal-panel__title">{label}</span>
        {isVrContext && <span className="signal-panel__live">LIVE</span>}
      </div>
      <div className="signal-panel__body">
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
