import { useState, useEffect, useRef, useMemo, type MouseEvent } from 'react'
import { IconWarn, IconCheck, IconArrowLeft, IconTrash } from '../components/icons'
import { signalTimeRate } from './signalTime'

interface Session {
  id: string
  participant: string
  notes: string
  started_at: string
  ended_at: string | null
  xdf_path: string | null
  video_path: string | null
  video_started_at?: string | null
  video_lsl_ts?: number | null
  video_lsl_ts_end?: number | null
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

// Numeric signal series recorded in the session's XDF (timestamps on the LSL clock).
interface Signals {
  channels: string[]
  timestamps: number[]
  series: Record<string, number[]>
}

// Highlight events within this many seconds of the video playhead.
const EVENT_WINDOW_S = 2

// ── helpers ───────────────────────────────────────────────────────────────────

function formatDuration(start: string, end: string | null): string {
  if (!end) return '—'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  return formatHMS(Math.round(ms / 1000))
}

function formatHMS(totalS: number): string {
  const s = Math.max(0, totalS)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function formatRelTime(sessionStart: string, occurred: string): string {
  return formatHMS(Math.round((new Date(occurred).getTime() - new Date(sessionStart).getTime()) / 1000))
}

function formatClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function formatVal(v: number | undefined): string {
  if (v === undefined || !Number.isFinite(v)) return '—'
  return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(3)
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

// ── recorded-signals chart (small multiples + a shared, video-synced cursor) ────

const CHART_W = 1000, CHART_H = 46  // viewBox units; SVG stretches to container width

// Closest index in a sorted-ascending array (binary search) — for the cursor value readout.
function nearestIndex(xs: number[], target: number): number {
  const n = xs.length
  if (n === 0) return 0
  if (target <= xs[0]) return 0
  if (target >= xs[n - 1]) return n - 1
  let lo = 0, hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (xs[mid] < target) lo = mid + 1
    else hi = mid
  }
  return lo > 0 && Math.abs(xs[lo - 1] - target) <= Math.abs(xs[lo] - target) ? lo - 1 : lo
}

function RealSignalChart({ signals, videoLslTs, videoLslTsEnd, videoDuration, playhead, showCursor, onSeek }: {
  signals: Signals
  videoLslTs: number | null
  videoLslTsEnd: number | null
  videoDuration: number
  playhead: number
  showCursor: boolean
  onSeek: (videoSeconds: number) => void
}) {
  // Static geometry — the per-channel SVG polylines and time axis. Recomputed ONLY when the
  // recorded data / alignment changes, never when the cursor moves. This is what keeps
  // seeking and scrubbing smooth: a playhead change no longer rebuilds every channel's path.
  const geom = useMemo(() => {
    const times = signals.timestamps
    if (times.length === 0 || signals.channels.length === 0) return null
    // Map each sample's LSL time to video media-time via the per-session drift rate (trusted
    // only when close to 1; a grossly-short/corrupt video falls back to 1:1 so the full
    // recorded signal data is plotted rather than compressed to the broken video length).
    const t0 = videoLslTs ?? times[0]
    const rate = signalTimeRate(videoLslTs, videoLslTsEnd, videoDuration)
    const xs = times.map((t) => (t - t0) / rate)
    const xMin = xs[0]
    const xMax = xs[xs.length - 1]
    const span = Math.max(0.001, xMax - xMin)
    const channels = signals.channels.map((name) => {
      const vals = signals.series[name] ?? []
      let vMin = Infinity, vMax = -Infinity
      for (const v of vals) { if (v < vMin) vMin = v; if (v > vMax) vMax = v }
      const vSpan = Math.max(1e-9, vMax - vMin)
      const pts = vals.map((v, i) => {
        const x = ((xs[i] - xMin) / span) * CHART_W
        const y = 3 + (CHART_H - 6) - ((v - vMin) / vSpan) * (CHART_H - 6)
        return `${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' ')
      return { name, vals, pts }
    })
    return { xs, xMin, xMax, span, channels }
  }, [signals, videoLslTs, videoLslTsEnd, videoDuration])

  if (!geom) {
    return <p className="empty-state" style={{ padding: 16 }}>No numeric signals recorded for this session.</p>
  }
  const { xs, xMin, span, channels } = geom

  // Cheap per-render bits that depend on the cursor position only.
  const inRange = showCursor && playhead >= xMin - 0.05 && playhead <= geom.xMax + 0.05
  const cursorFrac = Math.max(0, Math.min(1, (playhead - xMin) / span))
  const curIdx = inRange ? nearestIndex(xs, playhead) : 0

  function handleClick(e: MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const frac = (e.clientX - rect.left) / rect.width
    onSeek(xMin + Math.max(0, Math.min(1, frac)) * span)
  }

  return (
    <div className="signal-charts">
      {channels.map(({ name, vals, pts }) => (
        <div className="signal-chart-row" key={name}>
          <div className="signal-chart-row__head">
            <span className="signal-chart-row__name">{name}</span>
            <span className="signal-chart-row__value">{inRange ? formatVal(vals[curIdx]) : '—'}</span>
          </div>
          <svg
            viewBox={`0 0 ${CHART_W} ${CHART_H}`}
            preserveAspectRatio="none"
            className="signal-chart-svg"
            onClick={handleClick}
          >
            <polyline points={pts} fill="none" stroke="#4338ca" strokeWidth={1.5}
              vectorEffect="non-scaling-stroke" />
            {inRange && (
              <line x1={cursorFrac * CHART_W} x2={cursorFrac * CHART_W} y1={0} y2={CHART_H}
                stroke="#d4322a" strokeWidth={1} vectorEffect="non-scaling-stroke" />
            )}
          </svg>
        </div>
      ))}
    </div>
  )
}

// ── event display helpers ─────────────────────────────────────────────────────

const EVENT_STYLES: Record<string, { label: string; color: string; bg: string }> = {
  rule_fired:         { label: 'Adaptation Trigger', color: '#7c3aed', bg: 'rgba(124,58,237,0.12)' },
  action_fired:       { label: 'Action Invoked',     color: '#9333ea', bg: 'rgba(147,51,234,0.12)' },
  vr_context:         { label: 'Step Change',        color: '#0e7490', bg: 'rgba(14,116,144,0.12)' },
  link_status:        { label: 'Connectivity',       color: '#0369a1', bg: 'rgba(3,105,161,0.12)' },
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
      return Object.keys(f).slice(0, 3).map((k) => `${k}: ${f[k]}`).join(' · ')
    }
    if (obj.value !== undefined && obj.status) return `Set ${obj.status} → ${obj.value}`
    if (obj.link && obj.state) {
      return obj.detail ? `${String(obj.state)} — ${String(obj.detail)}` : String(obj.state)
    }
    const then = obj.then as { set?: Record<string, unknown> } | undefined
    if (then?.set) return `Set ${then.set.status} → ${then.set.value}`
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
        {warn && <span className="detail-stat__warn-icon"><IconWarn /></span>}
      </div>
      {sub && <div className="detail-stat__sub">{sub}</div>}
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export function DataHistory() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selected, setSelected] = useState<SessionDetail | null>(null)
  const [signals, setSignals] = useState<Signals | null>(null)
  const [playhead, setPlayhead] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)
  const [loading, setLoading] = useState(true)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    fetch('/api/sessions')
      .then((r) => r.json() as Promise<Session[]>)
      .then((data) => { setSessions(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  async function openSession(id: string) {
    setSignals(null)
    setPlayhead(0)
    setVideoDuration(0)
    const r = await fetch(`/api/sessions/${id}`)
    setSelected(await r.json() as SessionDetail)
    try {
      const sr = await fetch(`/api/sessions/${id}/signals`)
      setSignals(sr.ok ? (await sr.json() as Signals) : { channels: [], timestamps: [], series: {} })
    } catch {
      setSignals({ channels: [], timestamps: [], series: {} })
    }
  }

  function backToList() {
    setSelected(null)
    setSignals(null)
    setPlayhead(0)
    setVideoDuration(0)
  }

  async function deleteSession(id: string) {
    if (!window.confirm('Delete this session permanently? Its recording, signals and event log cannot be recovered.')) return
    const r = await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
    if (!r.ok) {
      const body = await r.json().catch(() => ({})) as { detail?: string }
      window.alert(`Delete failed: ${body.detail ?? `HTTP ${r.status}`}`)
      return
    }
    setSessions((prev) => prev.filter((s) => s.id !== id))
    if (selected?.id === id) backToList()
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
                <th>Participant</th><th>Started</th><th>Duration</th><th>Events</th><th>Status</th><th></th>
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
                  <td>
                    <div className="history-table__actions">
                      <button className="btn btn--small" onClick={(e) => { e.stopPropagation(); openSession(s.id) }}>View</button>
                      <button
                        className="btn btn--small btn--danger btn--icon"
                        onClick={(e) => { e.stopPropagation(); deleteSession(s.id) }}
                        disabled={s.status !== 'done'}
                        title={s.status !== 'done' ? 'Stop the session before deleting' : 'Delete this session'}
                        aria-label="Delete session"
                      >
                        <IconTrash />
                      </button>
                    </div>
                  </td>
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
  const hasVideo = !!s.video_path
  // Events are wall-clock; align them to the video via video_started_at (fallback: session start).
  const videoStartMs = Date.parse(s.video_started_at ?? s.started_at)
  const eventVideoTime = (ev: SessionEvent) => (Date.parse(ev.occurred_at) - videoStartMs) / 1000

  function seekTo(videoSeconds: number) {
    const v = videoRef.current
    if (!v) return
    const t = Math.max(0, videoSeconds)
    v.currentTime = t
    setPlayhead(t)
  }

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
        <button className="btn btn--small" onClick={backToList}><IconArrowLeft /> Back</button>
        <div className="detail-session-label">
          <span className="detail-session-id">{s.participant}</span>
          <span className="detail-session-date">{new Date(s.started_at).toLocaleDateString()}</span>
        </div>
        <div style={{ flex: 1 }} />
        <button
          className="btn btn--small btn--danger"
          onClick={() => deleteSession(s.id)}
          disabled={!isDone}
          title={!isDone ? 'Stop the session before deleting' : 'Delete this session'}
        >
          <IconTrash /> Delete
        </button>
        {s.xdf_path ? (
          <a className="btn btn--primary" href={`/api/sessions/${s.id}/download`} download>Download Report</a>
        ) : (
          <button className="btn btn--primary" disabled title="No export file available">Download Report</button>
        )}
      </div>

      <div className="detail-layout">
        <div className="detail-main">
          {/* recorded session video */}
          {hasVideo && (
            <div className="detail-chart-card">
              <div className="detail-chart-header">
                <span className="detail-chart-title">Session Video</span>
                <span className="detail-chart-legend">t = {formatClock(playhead)}</span>
              </div>
              <video
                ref={videoRef}
                controls
                className="detail-video"
                src={`/api/sessions/${s.id}/video`}
                onTimeUpdate={() => setPlayhead(videoRef.current?.currentTime ?? 0)}
                onSeeked={() => setPlayhead(videoRef.current?.currentTime ?? 0)}
                onLoadedMetadata={() => { const d = videoRef.current?.duration ?? 0; if (Number.isFinite(d)) setVideoDuration(d) }}
                onDurationChange={() => { const d = videoRef.current?.duration ?? 0; if (Number.isFinite(d)) setVideoDuration(d) }}
              />
            </div>
          )}

          {/* recorded signals, synced to the video */}
          <div className="detail-chart-card">
            <div className="detail-chart-header">
              <span className="detail-chart-title">Recorded Signals</span>
              {hasVideo && <span className="detail-chart-legend">cursor follows the video · click a chart to seek</span>}
            </div>
            {signals === null ? (
              <p className="empty-state" style={{ padding: 16 }}>Loading signals…</p>
            ) : (
              <RealSignalChart
                signals={signals}
                videoLslTs={s.video_lsl_ts ?? null}
                videoLslTsEnd={s.video_lsl_ts_end ?? null}
                videoDuration={videoDuration}
                playhead={playhead}
                showCursor={hasVideo}
                onSeek={seekTo}
              />
            )}
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
                    <tr><th>TIMESTAMP</th><th>EVENT</th><th>TRIGGER</th><th>RESPONSE</th></tr>
                  </thead>
                  <tbody>
                    {s.events.map((ev) => {
                      const style = getEventStyle(ev.event_type)
                      let cls = ''
                      if (hasVideo) {
                        const evt = eventVideoTime(ev)
                        if (Math.abs(evt - playhead) <= EVENT_WINDOW_S) cls = 'evlog-row--active'
                        else if (evt > playhead + EVENT_WINDOW_S) cls = 'evlog-row--future'
                      }
                      return (
                        <tr
                          key={ev.id}
                          className={cls}
                          onClick={hasVideo ? () => seekTo(eventVideoTime(ev)) : undefined}
                          style={hasVideo ? { cursor: 'pointer' } : undefined}
                          title={hasVideo ? 'Jump the video to this event' : undefined}
                        >
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
              {isDone ? <><IconCheck /> Verified</> : <><span className="status-dot status-dot--up" /> Active</>}
            </span>
          </div>

          <div className="detail-stats">
            <StatBox label="DURATION" value={formatDuration(s.started_at, s.ended_at)} />
            <StatBox label="ENVIRONMENT" value={`VR_SIM_${envSuffix}`} />
            <StatBox label="AVE. HRV" value={`${avgHrv} ms`} />
            <StatBox label="TOTAL ERRORS" value={String(warningCount + ruleFiredCount)} warn={warningCount > 0} />
            <StatBox label="MEAN FIXATION" value={`${meanFixation} /sec`} />
          </div>
        </div>
      </div>
    </div>
  )
}
