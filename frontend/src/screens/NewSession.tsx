import { useState } from 'react'
import { useVCoreStore } from '../ws/store'
import { LINK_ORDER, linkLabel } from '../ws/links'
import { IconPlay } from '../components/icons'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { statusBadgeVariant } from '@/lib/utils'

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

  // Show all canonical links (defaulting unreported ones to "down") so the System Status
  // panel always lists Sensor Pipeline, Unity WS and Browser WS — consistent with the
  // live monitor — instead of only the links already received over the socket.
  const systemLinks = LINK_ORDER.map((key) => ({
    name: linkLabel(key),
    state: linkStatuses[key]?.state ?? 'down',
  }))

  const allConnected = wsState === 'connected'

  return (
    <div className="screen">
      <div style={{ marginBottom: 18 }}>
        <div className="screen-title">Configure New Session</div>
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
              <Input
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
            <Badge variant={allConnected ? 'success' : 'warning'}>
              {allConnected ? 'READY' : 'AWAITING SYNC'}
            </Badge>
          </div>
          <div className="ns-panel__body" style={{ padding: '8px 14px' }}>
            {systemLinks.length === 0 ? (
              <p className="empty-state" style={{ padding: '8px 0' }}>No connections tracked.</p>
            ) : (
              systemLinks.map((link) => (
                <div key={link.name} className="link-status-row">
                  <span className={`status-dot status-dot--${link.state}`} />
                  <span className="link-status-row__name">{link.name}</span>
                  <Badge variant={statusBadgeVariant(link.state)}>{link.state}</Badge>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {error && <p className="form-error" style={{ marginBottom: 12 }}>{error}</p>}

      <div className="new-session-footer">
        <Button
          onClick={startSession}
          disabled={!participant.trim() || starting}
        >
          {starting ? 'Starting…' : <><IconPlay /> Start VR Session</>}
        </Button>
      </div>
    </div>
  )
}
