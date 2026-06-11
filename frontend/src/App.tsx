import { useState, useEffect, useRef } from 'react'
import { connectDashboard, disconnectDashboard } from './ws/socket'
import { useVCoreStore } from './ws/store'
import { SessionMonitor } from './screens/SessionMonitor'
import { RuleManager } from './screens/RuleManager'
import { NewSession } from './screens/NewSession'
import { DataHistory } from './screens/DataHistory'
import { SystemConfig } from './screens/SystemConfig'
import './App.css'

type Screen = 'monitor' | 'rules' | 'new-session' | 'history' | 'config'

const NAV: { id: Screen; label: string }[] = [
  { id: 'monitor', label: 'Session Monitor' },
  { id: 'rules', label: 'Rule Manager' },
  { id: 'history', label: 'Data History' },
  { id: 'config', label: 'System Config' },
]

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':')
}

function App() {
  const [screen, setScreen] = useState<Screen>('monitor')
  const activeSessionId = useVCoreStore((s) => s.activeSessionId)
  const setActiveSession = useVCoreStore((s) => s.setActiveSession)
  const [elapsed, setElapsed] = useState(0)
  const sessionStartRef = useRef<number | null>(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    connectDashboard(`${proto}://${host}/ws/dashboard`)
    return () => disconnectDashboard()
  }, [])

  useEffect(() => {
    if (activeSessionId) {
      sessionStartRef.current = Date.now()
      setElapsed(0)
    } else {
      sessionStartRef.current = null
      setElapsed(0)
    }
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSessionId) return
    const id = setInterval(() => {
      if (sessionStartRef.current) {
        setElapsed(Math.floor((Date.now() - sessionStartRef.current) / 1000))
      }
    }, 1000)
    return () => clearInterval(id)
  }, [activeSessionId])

  async function stopSession() {
    if (!activeSessionId) return
    await fetch(`/api/sessions/${activeSessionId}/stop`, { method: 'POST' })
    setActiveSession(null)
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <button
          className="btn btn--primary sidebar__new-session-btn"
          onClick={() => setScreen('new-session')}
        >
          + New Session
        </button>

        <nav className="sidebar__nav">
          {NAV.map(({ id, label }) => (
            <button
              key={id}
              className={`sidebar__link ${screen === id ? 'sidebar__link--active' : ''}`}
              onClick={() => setScreen(id)}
            >
              <span className="sidebar__link-dot" />
              {label}
            </button>
          ))}
        </nav>

      </aside>

      {/* Main content */}
      <div className="main-content">
        {/* Session status bar */}
        <div className="session-bar">
          {activeSessionId ? (
            <>
              <div className="session-bar__indicator">
                <span className="session-bar__dot" />
                <span className="session-bar__label">Session Active</span>
              </div>
              <span className="session-bar__timer">{formatTime(elapsed)}</span>
              <span className="session-bar__spacer" />
              <button className="btn btn--ghost btn--small">Pause</button>
              <button className="btn btn--danger btn--small" onClick={stopSession}>
                ● Stop Session
              </button>
            </>
          ) : (
            <div className="session-bar__indicator">
              <span className="session-bar__dot session-bar__dot--idle" />
              <span className="session-bar__label" style={{ opacity: 0.45, fontWeight: 400 }}>
                No active session
              </span>
            </div>
          )}
        </div>

        <main className="main">
          {screen === 'new-session' && (
            <NewSession onStarted={() => setScreen('monitor')} />
          )}
          {screen === 'monitor' && <SessionMonitor />}
          {screen === 'rules' && <RuleManager />}
          {screen === 'history' && <DataHistory />}
          {screen === 'config' && <SystemConfig />}
        </main>
      </div>
    </div>
  )
}

export default App
