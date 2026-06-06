import { useState, useEffect } from 'react'
import AgentStatusPanel from './AgentStatusPanel'
import TaskList from './TaskList'
import RequirementForm from './RequirementForm'
import AlertsPanel from './AlertsPanel'
import Dashboard from './Dashboard'
import { useWebSocket } from './useWebSocket'
import { apiUrl } from './api'
import './App.css'

interface HealthStatus {
  status: string
  app: string
  version: string
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [tab, setTab] = useState<'home' | 'agents' | 'tasks' | 'req' | 'alerts'>('home')
  const { lastMessage } = useWebSocket('/ws')

  useEffect(() => {
    fetch(apiUrl('/health'))
      .then(r => r.json())
      .then(setHealth)
      .catch(console.error)
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>OpenBoss</h1>
        <span className="version">v{health?.version || '...'}</span>
        <span className={`status ${health?.status}`}>
          {health?.status || 'connecting...'}
        </span>
      </header>
      <nav className="nav">
        <button className={tab === 'home' ? 'tab-active' : ''} onClick={() => setTab('home')}>Home</button>
        <button className={tab === 'agents' ? 'tab-active' : ''} onClick={() => setTab('agents')}>Agents</button>
        <button className={tab === 'tasks' ? 'tab-active' : ''} onClick={() => setTab('tasks')}>Tasks</button>
        <button className={tab === 'req' ? 'tab-active' : ''} onClick={() => setTab('req')}>New Req</button>
        <button className={tab === 'alerts' ? 'tab-active' : ''} onClick={() => setTab('alerts')}>Alerts</button>
        <span className="nav-spacer" />
        <a href="/api/requirements" target="_blank">Requirements</a>
        <a href="/api/alerts" target="_blank">Alerts</a>
        <a href="/docs" target="_blank">API Docs</a>
      </nav>
      <main className="main">
        {tab === 'home' ? <Dashboard /> : tab === 'agents' ? <AgentStatusPanel wsRefresh={lastMessage} /> : tab === 'tasks' ? <TaskList wsRefresh={lastMessage} /> : tab === 'req' ? <RequirementForm /> : <AlertsPanel />}
      </main>
    </div>
  )
}

export default App
