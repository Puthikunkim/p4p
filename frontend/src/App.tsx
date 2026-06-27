import { useState, useEffect } from 'react'
import { connectDashboard, disconnectDashboard } from './ws/socket'
import { useVCoreStore } from './ws/store'
import { SessionMonitor } from './screens/SessionMonitor'
import { RuleManager } from './screens/RuleManager'
import { NewSession } from './screens/NewSession'
import { DataHistory } from './screens/DataHistory'
import { SystemConfig } from './screens/SystemConfig'
import { VideoSessionProvider } from './video/VideoSessionProvider'
import {
  IconMonitor, IconRules, IconHistory, IconConfig,
  IconPlus, IconStop, IconPause, IconCore,
} from './components/icons'
import type { ComponentType, SVGProps } from 'react'
import './App.css'

type Screen = 'monitor' | 'rules' | 'new-session' | 'history' | 'config'

const NAV: { id: Screen; label: string; icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { id: 'monitor', label: 'Session Monitor', icon: IconMonitor },
  { id: 'rules', label: 'Rule Manager', icon: IconRules },
  { id: 'history', label: 'Data History', icon: IconHistory },
  { id: 'config', label: 'System Config', icon: IconConfig },
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
  const [prevSessionId, setPrevSessionId] = useState<string | null>(activeSessionId)

  // Reset the displayed timer the moment the active session changes. Adjusting
  // state during render (rather than in an effect) is React's recommended
  // pattern for "derive state from a changed value" and avoids a stale flash of
  // the previous session's time before the interval's first tick.
  if (activeSessionId !== prevSessionId) {
    setPrevSessionId(activeSessionId)
    setElapsed(0)
  }

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    connectDashboard(`${proto}://${host}/ws/dashboard`)
    return () => disconnectDashboard()
  }, [])

  useEffect(() => {
    if (!activeSessionId) return
    const start = Date.now()
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [activeSessionId])

  async function stopSession() {
    if (!activeSessionId) return
    const id = activeSessionId
    setActiveSession(null)  // optimistic: flip the UI to "stopped" instantly
    try {
      const r = await fetch(`/api/sessions/${id}/stop`, { method: 'POST' })
      if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`)
    } catch {
      setActiveSession(id)  // it didn't actually stop — put the session back
      window.alert('Failed to stop the session — please try again.')
    }
  }

  return (
    <VideoSessionProvider>
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__brand-mark"><IconCore /></span>
          <span className="sidebar__brand-text">
            V<span className="sidebar__brand-sep">·</span>CORE
          </span>
        </div>

        <button
          className="btn btn--primary sidebar__new-session-btn"
          onClick={() => setScreen('new-session')}
        >
          <IconPlus /> New Session
        </button>

        <nav className="sidebar__nav">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`sidebar__link ${screen === id ? 'sidebar__link--active' : ''}`}
              onClick={() => setScreen(id)}
            >
              <span className="sidebar__link-icon"><Icon /></span>
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
              <button className="btn btn--ghost btn--small"><IconPause /> Pause</button>
              <button className="btn btn--danger btn--small" onClick={stopSession}>
                <IconStop /> Stop Session
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
    </VideoSessionProvider>
  )
}

export default App
