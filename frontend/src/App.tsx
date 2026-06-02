import { useState, useEffect } from 'react'
import AgentStatusPanel from './AgentStatusPanel'
import TaskList from './TaskList'
import './App.css'

interface HealthStatus {
  status: string
  app: string
  version: string
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [tab, setTab] = useState<'agents' | 'tasks'>('agents')

  useEffect(() => {
    fetch('/health')
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
        <button className={tab === 'agents' ? 'tab-active' : ''} onClick={() => setTab('agents')}>Agents</button>
        <button className={tab === 'tasks' ? 'tab-active' : ''} onClick={() => setTab('tasks')}>Tasks</button>
        <span className="nav-spacer" />
        <a href="/api/requirements" target="_blank">Requirements</a>
        <a href="/api/alerts" target="_blank">Alerts</a>
        <a href="/docs" target="_blank">API Docs</a>
      </nav>
      <main className="main">
        {tab === 'agents' ? <AgentStatusPanel /> : <TaskList />}
      </main>
    </div>
  )
}

export default App
