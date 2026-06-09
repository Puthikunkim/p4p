import { useState } from 'react'

type Status = 'idle' | 'running' | 'done'

export function NewSession() {
  const [participant, setParticipant] = useState('')
  const [notes, setNotes] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function startSession() {
    setError(null)
    const resp = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant, notes }),
    })
    if (!resp.ok) {
      const body = await resp.json() as { detail?: string }
      setError(body.detail ?? `HTTP ${resp.status}`)
      return
    }
    const { session_id } = await resp.json() as { session_id: string }
    setSessionId(session_id)
    setStatus('running')
  }

  async function stopSession() {
    if (!sessionId) return
    await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST' })
    setStatus('done')
  }

  function reset() {
    setStatus('idle')
    setSessionId(null)
    setParticipant('')
    setNotes('')
  }

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>New Session</h2>
        <span className={`badge badge--${status}`}>{status}</span>
      </div>

      {status === 'idle' && (
        <div className="form-panel">
          <div className="form-row">
            <label>Participant ID</label>
            <input value={participant} onChange={(e) => setParticipant(e.target.value)}
              placeholder="P01" />
          </div>
          <div className="form-row">
            <label>Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
              rows={3} placeholder="Condition, environment, …" />
          </div>
          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button className="btn btn--primary" onClick={startSession}
              disabled={!participant.trim()}>
              Start Session
            </button>
          </div>
        </div>
      )}

      {status === 'running' && (
        <div className="session-running">
          <p>Recording <strong>{participant}</strong></p>
          <p className="session-id-label">Session ID: <code>{sessionId}</code></p>
          <button className="btn btn--danger" onClick={stopSession}>Stop Session</button>
        </div>
      )}

      {status === 'done' && (
        <div className="session-done">
          <p>Session saved. View it in Data History.</p>
          <button className="btn" onClick={reset}>New Session</button>
        </div>
      )}
    </div>
  )
}
