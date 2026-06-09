import { useState, useEffect } from 'react'

interface Session {
  id: string
  participant: string
  notes: string
  started_at: string
  ended_at: string | null
  xdf_path: string | null
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

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Data History</h2>
        {selected && (
          <button className="btn btn--small" onClick={() => setSelected(null)}>← Back</button>
        )}
      </div>

      {!selected ? (
        sessions.length === 0 ? (
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
                <tr key={s.id}>
                  <td>{s.participant}</td>
                  <td>{new Date(s.started_at).toLocaleString()}</td>
                  <td>{s.ended_at ? formatDuration(s.started_at, s.ended_at) : '—'}</td>
                  <td>{s.event_count}</td>
                  <td><span className={`badge badge--${s.status === 'done' ? 'done' : 'running'}`}>{s.status}</span></td>
                  <td><button className="btn btn--small" onClick={() => openSession(s.id)}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : (
        <div className="session-detail">
          <div className="session-detail__meta">
            <div><strong>Participant:</strong> {selected.participant}</div>
            {selected.notes && <div><strong>Notes:</strong> {selected.notes}</div>}
            <div><strong>Started:</strong> {new Date(selected.started_at).toLocaleString()}</div>
            {selected.ended_at && <div><strong>Ended:</strong> {new Date(selected.ended_at).toLocaleString()}</div>}
            {selected.xdf_path && <div><strong>XDF:</strong> <code>{selected.xdf_path}</code></div>}
          </div>

          <h3>Events ({selected.events.length})</h3>
          {selected.events.length === 0 ? (
            <p className="empty-state">No events recorded.</p>
          ) : (
            <table className="history-table">
              <thead>
                <tr><th>Time</th><th>Type</th><th>Source</th><th>Payload</th></tr>
              </thead>
              <tbody>
                {selected.events.map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.occurred_at).toLocaleTimeString()}</td>
                    <td><span className="event-type-badge">{e.event_type}</span></td>
                    <td>{e.source}</td>
                    <td><code className="payload-preview">{e.payload}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}
