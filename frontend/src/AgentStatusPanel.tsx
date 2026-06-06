import { useState, useEffect } from 'react'
import TerminalViewer from './TerminalViewer'
import { apiUrl } from './api'
import './AgentStatusPanel.css'

interface AgentInfo {
  task_id: string
  status: string
  role: string
  started: string | null
  finished: string | null
  git_sha: string | null
  error: string | null
}

interface AgentsResponse {
  agents: AgentInfo[]
  summary: { total: number; completed: number; failed: number; in_progress: number; blocked: number }
  by_role: { role: string; total: number; completed: number; failed: number; last_active: string | null }[]
}

const STATUS_COLORS: Record<string, string> = {
  COMPLETED: '#22c55e',
  FAILED: '#ef4444',
  IN_PROGRESS: '#3b82f6',
  BLOCKED: '#f59e0b',
  PENDING: '#6b7280',
}

function formatDuration(started: string | null, finished: string | null): string {
  if (!started || !finished) return '-'
  const s = new Date(started).getTime()
  const f = new Date(finished).getTime()
  const sec = Math.round((f - s) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

interface Props { wsRefresh?: string | null }

export default function AgentStatusPanel({ wsRefresh }: Props) {
  const [data, setData] = useState<AgentsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const fetchAgents = () => {
      fetch(apiUrl('/api/agents'))
        .then(r => r.json())
        .then(d => { if (!cancelled) { setData(d); setError(null) } })
        .catch(e => { if (!cancelled) setError(e.message) })
    }

    fetchAgents()
    const timer = setInterval(fetchAgents, 5000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [wsRefresh])

  if (error) return <div className="panel-error">Failed to load agents: {error}</div>
  if (!data) return <div className="panel-loading">Loading agents...</div>

  const { agents, summary, by_role } = data

  return (
    <div className="agent-panel">
      <h2>Agents <span className="summary-badge">{summary.completed}/{summary.total} done</span></h2>

      <table className="agent-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Role</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Git</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {agents.map(a => (
            <tr key={a.task_id}>
              <td className="task-id">{a.task_id}</td>
              <td>{a.role}</td>
              <td>
                <span className="status-badge" style={{ background: STATUS_COLORS[a.status] || '#6b7280' }}>
                  {a.status}
                </span>
              </td>
              <td>{formatDuration(a.started, a.finished)}</td>
              <td className="git-sha">{a.git_sha?.slice(0, 7) || '-'}</td>
              <td><TerminalViewer agentId={a.task_id} /></td>
            </tr>
          ))}
          {agents.length === 0 && (
            <tr><td colSpan={6} className="empty">No agents yet.</td></tr>
          )}
        </tbody>
      </table>

      <div className="by-role">
        <h3>By Role</h3>
        {by_role.map(r => (
          <div key={r.role} className="role-row">
            <span className="role-name">{r.role}</span>
            <span className="role-stats">{r.total} tasks ({r.completed} done, {r.failed} failed)</span>
          </div>
        ))}
      </div>
    </div>
  )
}
