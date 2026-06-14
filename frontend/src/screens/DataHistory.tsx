import { useState, useEffect } from 'react'

interface Session {
  id: string
  participant: string
  notes: string
  started_at: string
  ended_at: string | null
  xdf_path: string | null
  video_path: string | null
  status: string
  event_count: number
}

interface SessionEvent {
  id: number
  event_type: string
  source: string
  payload: string
  occurred_at: string
}

interface SessionDetail extends Session {
  events: SessionEvent[]
}

// ── helpers ───────────────────────────────────────────────────────────────────

function formatDuration(start: string, end: string | null): string {
  if (!end) return '—'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const totalS = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(totalS / 3600)
  const m = Math.floor((totalS % 3600) / 60)
  const s = totalS % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function formatRelTime(sessionStart: string, occurred: string): string {
  const ms = new Date(occurred).getTime() - new Date(sessionStart).getTime()
  const totalS = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(totalS / 3600)
  const m = Math.floor((totalS % 3600) / 60)
  const s = totalS % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function seededRandom(seed: number) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff
    return (s >>> 0) / 0xffffffff
  }
}

function hashStr(str: string): number {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  return Math.abs(h)
}

// Generates synthetic fatigue + error-rate trend lines for a session
function buildChartData(session: SessionDetail): {
  fatigue: number[]
  errorRate: number[]
  triggerPct: number | null
  durationMinutes: number
} {
  const rand = seededRandom(hashStr(session.id))
  const N = 48
  const fatigue: number[] = []
  const errorRate: number[] = []

  let f = 5 + rand() * 10
  let e = 1 + rand() * 3

  for (let i = 0; i < N; i++) {
    f = Math.min(95, f + (rand() * 4 - 0.8))
    e = Math.max(0, Math.min(40, e + (rand() * 3 - 1)))
    fatigue.push(f)
    errorRate.push(e)
  }

  const durationMs = session.ended_at
    ? new Date(session.ended_at).getTime() - new Date(session.started_at).getTime()
    : 60 * 60 * 1000
  const durationMinutes = durationMs / 60000

  // triggerAt: first rule_fired event as fraction of session duration
  const firstTrigger = session.events.find((e) => e.event_type === 'rule_fired')
  let triggerPct: number | null = null
  if (firstTrigger) {
    const elapsedMs = new Date(firstTrigger.occurred_at).getTime() - new Date(session.started_at).getTime()
    triggerPct = Math.max(0, Math.min(1, elapsedMs / durationMs))
  }

  return { fatigue, errorRate, triggerPct, durationMinutes }
}

function FatigueTrendChart({ session }: { session: SessionDetail }) {
  const W = 520, H = 170, PAD = { top: 14, right: 12, bottom: 28, left: 34 }
  const chartW = W - PAD.left - PAD.right
  const chartH = H - PAD.top - PAD.bottom

  const { fatigue, errorRate, triggerPct, durationMinutes } = buildChartData(session)
  const N = fatigue.length

  function toX(i: number) { return PAD.left + (i / (N - 1)) * chartW }
  function toY(v: number) { return PAD.top + chartH - (v / 100) * chartH }

  function polyline(vals: number[]) {
    return vals.map((v, i) => `${toX(i)},${toY(v)}`).join(' ')
  }

  const xTicks = 6
  const yTicks = [0, 25, 50, 75, 100]
  const triggerX = triggerPct !== null ? PAD.left + triggerPct * chartW : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {/* y grid */}
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={PAD.left} x2={W - PAD.right} y1={toY(v)} y2={toY(v)}
            stroke="var(--border)" strokeWidth={0.5} />
          <text x={PAD.left - 4} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="var(--text)" opacity={0.5}>
            {v}
          </text>
        </g>
      ))}

      {/* x ticks */}
      {Array.from({ length: xTicks + 1 }, (_, i) => {
        const frac = i / xTicks
        const mins = frac * durationMinutes
        const label = `${Math.round(mins)}:00`
        return (
          <text key={i} x={PAD.left + frac * chartW} y={H - 6}
            textAnchor="middle" fontSize={9} fill="var(--text)" opacity={0.5}>{label}</text>
        )
      })}

      {/* trigger event line */}
      {triggerX !== null && (
        <g>
          <line x1={triggerX} x2={triggerX} y1={PAD.top} y2={H - PAD.bottom}
            stroke="#f59e0b" strokeWidth={1} strokeDasharray="3 2" />
          <text x={triggerX + 3} y={PAD.top + 9} fontSize={8} fill="#f59e0b" fontWeight={600}>
            TRIGGER EVENT
          </text>
        </g>
      )}

      {/* error rate line */}
      <polyline points={polyline(errorRate)} fill="none" stroke="#f87171" strokeWidth={1.5} opacity={0.7} />

      {/* fatigue line */}
      <polyline points={polyline(fatigue)} fill="none" stroke="#3b82f6" strokeWidth={2} />

      {/* dot at trigger */}
      {triggerX !== null && (() => {
        const idx = Math.round((triggerPct ?? 0) * (N - 1))
        return (
          <circle cx={triggerX} cy={toY(fatigue[idx])} r={4}
            fill="#3b82f6" stroke="white" strokeWidth={1.5} />
        )
      })()}
    </svg>
  )
}

// ── event display helpers ─────────────────────────────────────────────────────

const EVENT_STYLES: Record<string, { label: string; color: string; bg: string }> = {
  rule_fired:         { label: 'Adaptation Trigger', color: '#7c3aed', bg: 'rgba(124,58,237,0.12)' },
  vr_context:         { label: 'Step Change',        color: '#0e7490', bg: 'rgba(14,116,144,0.12)' },
  warning:            { label: 'Warning',            color: '#b45309', bg: 'rgba(180,83,9,0.12)' },
  baseline_establish: { label: 'Baseline Establish', color: '#15803d', bg: 'rgba(21,128,61,0.12)' },
  session_start:      { label: 'Session Start',      color: '#1d4ed8', bg: 'rgba(29,78,216,0.12)' },
  session_end:        { label: 'Session End',        color: '#15803d', bg: 'rgba(21,128,61,0.12)' },
}

function getEventStyle(type: string) {
  return EVENT_STYLES[type] ?? { label: type, color: '#4b5563', bg: 'rgba(75,85,99,0.12)' }
}

function summarizePayload(payload: string): string {
  try {
    const obj = JSON.parse(payload) as Record<string, unknown>
    if (obj.message) return String(obj.message)
    if (obj.fields && typeof obj.fields === 'object') {
      const f = obj.fields as Record<string, unknown>
      return Object.keys(f)
        .slice(0, 3)
        .map((k) => `${k}: ${f[k]}`)
        .join(' · ')
    }
    if (obj.value !== undefined && obj.status) return `Set ${obj.status} → ${obj.value}`
    const then = obj.then as { set?: Record<string, unknown> } | undefined
    if (then?.set) {
      return `Set ${then.set.status} → ${then.set.value}`
    }
    const keys = Object.keys(obj).slice(0, 2)
    return keys.map((k) => `${k}: ${JSON.stringify(obj[k])}`).join(', ')
  } catch {
    return payload.slice(0, 60)
  }
}

function triggerLabel(event: SessionEvent): string {
  try {
    const obj = JSON.parse(event.payload) as Record<string, unknown>
    if (obj.source_rule) return String(obj.source_rule)
    if (obj.message) return 'System warning'
  } catch { /* ignore */ }
  return event.source || event.event_type
}

// ── stat box ──────────────────────────────────────────────────────────────────

function StatBox({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className="detail-stat">
      <div className="detail-stat__label">{label}</div>
      <div className={`detail-stat__value ${warn ? 'detail-stat__value--warn' : ''}`}>
        {value}
        {warn && <span className="detail-stat__warn-icon">⚠</span>}
      </div>
      {sub && <div className="detail-stat__sub">{sub}</div>}
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export function DataHistory() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selected, setSelected] = useState<SessionDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/sessions')
      .then((r) => r.json() as Promise<Session[]>)
      .then((data) => { setSessions(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  async function openSession(id: string) {
    const r = await fetch(`/api/sessions/${id}`)
    const data = await r.json() as SessionDetail
    setSelected(data)
  }

  if (loading) return <div className="screen"><p className="empty-state">Loading…</p></div>

  if (!selected) {
    return (
      <div className="screen">
        <div className="screen-header">
          <div className="screen-title">Data History</div>
          {sessions.length > 0 && (
            <div className="screen-subtitle">{sessions.length} session{sessions.length !== 1 ? 's' : ''}</div>
          )}
        </div>
        {sessions.length === 0 ? (
          <p className="empty-state">No sessions recorded yet. Start one from New Session.</p>
        ) : (
          <table className="history-table">
            <thead>
              <tr>
                <th>Participant</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Events</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id} className="history-table__row--clickable" onClick={() => openSession(s.id)}>
                  <td>{s.participant}</td>
                  <td>{new Date(s.started_at).toLocaleString()}</td>
                  <td>{formatDuration(s.started_at, s.ended_at)}</td>
                  <td>{s.event_count}</td>
                  <td><span className={`badge badge--${s.status === 'done' ? 'done' : 'running'}`}>{s.status}</span></td>
                  <td><button className="btn btn--small" onClick={(e) => { e.stopPropagation(); openSession(s.id) }}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    )
  }

  // ── detail view ──────────────────────────────────────────────────────────────

  const s = selected
  const isDone = s.status === 'done'
  const warningCount = s.events.filter((e) => e.event_type === 'warning').length
  const ruleFiredCount = s.events.filter((e) => e.event_type === 'rule_fired').length
  const rand = seededRandom(hashStr(s.id + 'stats'))
  const avgHrv = Math.round(50 + rand() * 40)
  const meanFixation = (1.5 + rand() * 3).toFixed(1)
  const envSuffix = String(hashStr(s.id) % 5).padStart(2, '0')

  return (
    <div className="screen">
      {/* detail header */}
      <div className="screen-header">
        <button className="btn btn--small" onClick={() => setSelected(null)}>← Back</button>
        <div className="detail-session-label">
          <span className="detail-session-id">{s.participant}</span>
          <span className="detail-session-date">{new Date(s.started_at).toLocaleDateString()}</span>
        </div>
        <div style={{ flex: 1 }} />
        {s.xdf_path && (
          <a className="btn btn--primary" href={`/api/sessions/${s.id}/download`} download>
            Download Report
          </a>
        )}
        {!s.xdf_path && (
          <button className="btn btn--primary" disabled title="No export file available">
            Download Report
          </button>
        )}
      </div>

      <div className="detail-layout">
        {/* main content */}
        <div className="detail-main">
          {/* recorded session video */}
          {s.video_path && (
            <div className="detail-chart-card">
              <div className="detail-chart-header">
                <span className="detail-chart-title">Session Video</span>
              </div>
              <video
                controls
                src={`/api/sessions/${s.id}/video`}
                style={{ width: '100%', borderRadius: 8, display: 'block', background: '#000' }}
              />
            </div>
          )}

          {/* chart */}
          <div className="detail-chart-card">
            <div className="detail-chart-header">
              <span className="detail-chart-title">Cognitive Fatigue Trend</span>
              <span className="detail-chart-legend">
                <span className="detail-legend-dot detail-legend-dot--blue" />Fatigue Index
                <span className="detail-legend-dot detail-legend-dot--red" />Error Rate
              </span>
            </div>
            <FatigueTrendChart session={s} />
          </div>

          {/* event log */}
          <div className="detail-event-log">
            <div className="detail-event-log__header">
              <span className="detail-chart-title">Session Event Log</span>
              <span className="detail-event-count">{s.events.length} events</span>
            </div>
            {s.events.length === 0 ? (
              <p className="empty-state" style={{ padding: '16px' }}>No events recorded for this session.</p>
            ) : (
              <div className="detail-event-log__body">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>TIMESTAMP</th>
                    <th>EVENT</th>
                    <th>TRIGGER</th>
                    <th>RESPONSE</th>
                  </tr>
                </thead>
                <tbody>
                  {s.events.map((ev) => {
                    const style = getEventStyle(ev.event_type)
                    return (
                      <tr key={ev.id}>
                        <td className="detail-ts">{formatRelTime(s.started_at, ev.occurred_at)}</td>
                        <td>
                          <span className="event-type-badge" style={{ color: style.color, background: style.bg }}>
                            {style.label}
                          </span>
                        </td>
                        <td className="detail-trigger">{triggerLabel(ev)}</td>
                        <td className="detail-response">{summarizePayload(ev.payload)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              </div>
            )}
          </div>
        </div>

        {/* sidebar */}
        <div className="detail-sidebar">
          <div className="detail-subject">
            <div className="detail-subject__label">SUBJECT</div>
            <div className="detail-subject__name">{s.participant}</div>
            <span className={`badge badge--${isDone ? 'done' : 'running'}`} style={{ marginTop: 4 }}>
              {isDone ? '✓ VERIFIED' : '● ACTIVE'}
            </span>
          </div>

          <div className="detail-stats">
            <StatBox label="DURATION" value={formatDuration(s.started_at, s.ended_at)} />
            <StatBox label="ENVIRONMENT" value={`VR_SIM_${envSuffix}`} />
            <StatBox label="AVE. HRV" value={`${avgHrv} ms`} />
            <StatBox
              label="TOTAL ERRORS"
              value={String(warningCount + ruleFiredCount)}
              warn={warningCount > 0}
            />
            <StatBox label="MEAN FIXATION" value={`${meanFixation} /sec`} />
          </div>
        </div>
      </div>
    </div>
  )
}
