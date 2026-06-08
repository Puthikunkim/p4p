import { useState, useEffect } from 'react'
import { connectDashboard, disconnectDashboard } from './ws/socket'
import { SessionMonitor } from './screens/SessionMonitor'
import { RuleManager } from './screens/RuleManager'
import { NewSession } from './screens/NewSession'
import { DataHistory } from './screens/DataHistory'
import { SystemConfig } from './screens/SystemConfig'
import './App.css'

type Screen = 'monitor' | 'rules' | 'new-session' | 'history' | 'config'

const NAV: { id: Screen; label: string }[] = [
  { id: 'new-session', label: 'New Session' },
  { id: 'monitor', label: 'Session Monitor' },
  { id: 'rules', label: 'Rule Manager' },
  { id: 'history', label: 'Data History' },
  { id: 'config', label: 'System Config' },
]

function App() {
  const [screen, setScreen] = useState<Screen>('monitor')

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    connectDashboard(`${proto}://${host}/ws/dashboard`)
    return () => disconnectDashboard()
  }, [])

  return (
    <div className="app">
      <nav className="nav">
        <span className="nav__brand">V-CORE</span>
        <div className="nav__links">
          {NAV.map(({ id, label }) => (
            <button
              key={id}
              className={`nav__link ${screen === id ? 'nav__link--active' : ''}`}
              onClick={() => setScreen(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>

      <main className="main">
        {screen === 'new-session' && <NewSession />}
        {screen === 'monitor' && <SessionMonitor />}
        {screen === 'rules' && <RuleManager />}
        {screen === 'history' && <DataHistory />}
        {screen === 'config' && <SystemConfig />}
      </main>
    </div>
  )
}

export default App
