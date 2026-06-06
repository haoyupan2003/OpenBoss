import { useState, useEffect } from 'react'
import { apiUrl } from './api'
import './Dashboard.css'

interface DashboardData {
  health: { app: string; version: string; status: string } | null
  agents: { total: number; completed: number; failed: number; in_progress: number; blocked: number } | null
  tasks: { total: number; completed: number; failed: number; pending: number; in_progress: number } | null
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData>({ health: null, agents: null, tasks: null })

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetch(apiUrl('/health')).then(r => r.json()).catch(() => null),
      fetch(apiUrl('/api/agents')).then(r => r.json()).then(d => d.summary).catch(() => null),
      fetch(apiUrl('/api/tasks')).then(r => r.json()).then(d => d.summary).catch(() => null),
    ]).then(([health, agents, tasks]) => {
      if (!cancelled) setData({ health, agents, tasks })
    })
    return () => { cancelled = true }
  }, [])

  const { health, agents, tasks } = data

  return (
    <div className="dashboard">
      <h2>System Overview</h2>

      <div className="db-cards">
        <div className="db-card health">
          <div className="db-card-label">System</div>
          <div className="db-card-value">{health?.app || '...'}</div>
          <div className="db-card-sub">v{health?.version || '?'} · {health?.status || 'connecting'}</div>
        </div>

        <div className="db-card">
          <div className="db-card-label">Agents</div>
          <div className="db-card-value">{agents?.total ?? '-'}</div>
          <div className="db-card-sub">
            <span className="green">{agents?.completed ?? 0} done</span>
            {agents?.failed ? <span className="red"> · {agents.failed} failed</span> : null}
          </div>
        </div>

        <div className="db-card">
          <div className="db-card-label">Tasks</div>
          <div className="db-card-value">{tasks?.total ?? '-'}</div>
          <div className="db-card-sub">
            <span className="green">{tasks?.completed ?? 0} done</span>
            {tasks?.failed ? <span className="red"> · {tasks.failed} failed</span> : null}
            {tasks?.pending ? <span className="dim"> · {tasks.pending} pending</span> : null}
          </div>
        </div>

        <div className="db-card">
          <div className="db-card-label">Completion</div>
          <div className="db-card-value">
            {tasks ? Math.round((tasks.completed / Math.max(tasks.total, 1)) * 100) + '%' : '-'}
          </div>
          <div className="db-bar">
            <div className="db-bar-fill" style={{
              width: tasks && tasks.total > 0 ? `${Math.round((tasks.completed / tasks.total) * 100)}%` : '0%'
            }} />
          </div>
        </div>
      </div>

      <div className="db-detail">
        {agents && (
          <div className="db-section">
            <h3>Agents</h3>
            <div className="db-stats">
              <span>Total: {agents.total}</span>
              <span className="green">Completed: {agents.completed}</span>
              <span className="red">Failed: {agents.failed}</span>
              <span className="blue">Running: {agents.in_progress}</span>
              <span className="yellow">Blocked: {agents.blocked}</span>
            </div>
          </div>
        )}
        {tasks && (
          <div className="db-section">
            <h3>Tasks</h3>
            <div className="db-stats">
              <span>Total: {tasks.total}</span>
              <span className="green">Completed: {tasks.completed}</span>
              <span className="red">Failed: {tasks.failed}</span>
              <span className="blue">Running: {tasks.in_progress}</span>
              <span className="dim">Pending: {tasks.pending}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
