import { useState } from 'react'
import { useVCoreStore } from '../ws/store'
import { IconPlay } from '../components/icons'

interface Props {
  onStarted?: () => void
}

export function NewSession({ onStarted }: Props) {
  const [participant, setParticipant] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const activeSessionId = useVCoreStore((s) => s.activeSessionId)
  const linkStatuses = useVCoreStore((s) => s.linkStatuses)
  const wsState = useVCoreStore((s) => s.wsState)
  const setActiveSession = useVCoreStore((s) => s.setActiveSession)

  if (activeSessionId) {
    return (
      <div className="screen">
        <div style={{ marginBottom: 6 }}>
          <div className="screen-title">Session In Progress</div>
          <div className="screen-subtitle">A session is already running. Stop it from the header bar to start a new one.</div>
        </div>
      </div>
    )
  }

  async function startSession() {
    setError(null)
    setStarting(true)
    try {
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
      setActiveSession(session_id)
      onStarted?.()
    } catch (e) {
      setError(String(e))
    } finally {
      setStarting(false)
    }
  }

  const systemLinks = Object.entries(linkStatuses).map(([key, ls]) => ({
    name: key,
    state: ls.state,
    detail: ls.detail ?? null,
  }))

  const allConnected = wsState === 'connected'

  return (
    <div className="screen">
      <div style={{ marginBottom: 18 }}>
        <div className="screen-title">Configure New Session</div>
        <div className="screen-subtitle">Setup parameters for the upcoming VR monitoring sequence.</div>
      </div>

      <div className="new-session-grid">
        {/* Left: Participant Details */}
        <div className="ns-panel">
          <div className="ns-panel__header">
            <span>Participant Details</span>
          </div>
          <div className="ns-panel__body">
            <div className="ns-panel__row">
              <label className="ns-panel__label">Subject ID</label>
              <input
                className="ns-panel__input"
                value={participant}
                onChange={(e) => setParticipant(e.target.value)}
                placeholder="e.g. SUBJ-0042"
              />
            </div>
            <div className="ns-panel__row">
              <label className="ns-panel__label">Pre-session Notes</label>
              <textarea
                className="ns-panel__textarea"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
                placeholder="Researcher observations, condition, environment…"
              />
            </div>
          </div>
        </div>

        {/* Right: System Status */}
        <div className="ns-panel">
          <div className="ns-panel__header">
            <span>System Status</span>
            <span className={`ns-panel__badge ${allConnected ? 'ns-panel__badge--ok' : ''}`}>
              {allConnected ? 'READY' : 'AWAITING SYNC'}
            </span>
          </div>
          <div className="ns-panel__body" style={{ padding: '8px 14px' }}>
            {systemLinks.length === 0 ? (
              <p className="empty-state" style={{ padding: '8px 0' }}>No connections tracked.</p>
            ) : (
              systemLinks.map((link) => (
                <div key={link.name} className="link-status-row">
                  <span className={`status-dot status-dot--${link.state}`} />
                  <span className="link-status-row__name">{link.name}</span>
                  <span className={`badge badge--${link.state}`}>{link.state}</span>
                  {link.detail && (
                    <span className="link-status-row__detail">{link.detail}</span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {error && <p className="form-error" style={{ marginBottom: 12 }}>{error}</p>}

      <div className="new-session-footer">
        <button
          className="btn btn--primary"
          onClick={startSession}
          disabled={!participant.trim() || starting}
        >
          {starting ? 'Starting…' : <><IconPlay /> Start VR Session</>}
        </button>
      </div>
    </div>
  )
}
