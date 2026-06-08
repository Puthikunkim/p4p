import { useState } from 'react'

export function NewSession() {
  const [participantId, setParticipantId] = useState('')
  const [notes, setNotes] = useState('')
  const [status, setStatus] = useState<'idle' | 'running' | 'done'>('idle')

  function startSession() {
    if (!participantId.trim()) return
    setStatus('running')
  }

  function stopSession() {
    setStatus('done')
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
            <input
              value={participantId}
              onChange={(e) => setParticipantId(e.target.value)}
              placeholder="P01"
            />
          </div>
          <div className="form-row">
            <label>Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Condition, environment, …"
            />
          </div>
          <div className="form-actions">
            <button
              className="btn btn--primary"
              onClick={startSession}
              disabled={!participantId.trim()}
            >
              Start Session
            </button>
          </div>
        </div>
      )}

      {status === 'running' && (
        <div className="session-running">
          <p>Recording <strong>{participantId}</strong>…</p>
          <button className="btn btn--danger" onClick={stopSession}>Stop Session</button>
        </div>
      )}

      {status === 'done' && (
        <div className="session-done">
          <p>Session saved.</p>
          <button className="btn" onClick={() => setStatus('idle')}>New Session</button>
        </div>
      )}
    </div>
  )
}
