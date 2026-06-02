import { useState, useEffect } from 'react'
import './TaskList.css'

interface TaskInfo {
  id: string
  title: string
  status: string
  priority: string
  complexity: string
  suggested_role: string
  dependencies: string[]
  progress: {
    status: string; role: string; git_sha: string | null
    started: string | null; finished: string | null; error: string | null
  } | null
}

interface TasksResponse {
  tasks: TaskInfo[]
  summary: { total: number; completed: number; failed: number; pending: number; in_progress: number; blocked: number }
}

const STATUSES = ['ALL', 'COMPLETED', 'FAILED', 'PENDING', 'IN_PROGRESS', 'BLOCKED'] as const
const STATUS_COLORS: Record<string, string> = {
  completed: '#22c55e', failed: '#ef4444', in_progress: '#3b82f6',
  blocked: '#f59e0b', pending: '#6b7280',
}

export default function TaskList() {
  const [data, setData] = useState<TasksResponse | null>(null)
  const [filter, setFilter] = useState<string>('ALL')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const params = filter !== 'ALL' ? `?status=${filter}` : ''
    let cancelled = false
    fetch(`/api/tasks${params}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) { setData(d); setError(null) } })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [filter])

  if (error) return <div className="tl-error">Failed to load tasks: {error}</div>
  if (!data) return <div className="tl-loading">Loading tasks...</div>

  const { tasks, summary } = data

  return (
    <div className="task-list">
      <h2>Tasks <span className="tl-summary">{summary.completed}/{summary.total} done</span></h2>

      <div className="tl-filters">
        {STATUSES.map(s => (
          <button key={s} className={filter === s ? 'active' : ''} onClick={() => setFilter(s)}>
            {s}
          </button>
        ))}
      </div>

      <table className="tl-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Status</th>
            <th>Role</th>
            <th>Git</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(t => (
            <tr key={t.id}>
              <td className="tl-id">{t.id}</td>
              <td>
                <div className="tl-title">{t.title}</div>
                {t.dependencies.length > 0 && (
                  <div className="tl-deps">deps: {t.dependencies.join(', ')}</div>
                )}
              </td>
              <td>
                <span className="tl-status" style={{ background: STATUS_COLORS[t.status] || '#6b7280' }}>
                  {t.status}
                </span>
                {t.progress?.error && <div className="tl-error-msg">{t.progress.error.slice(0, 40)}</div>}
              </td>
              <td>{t.progress?.role || t.suggested_role || '-'}</td>
              <td className="tl-sha">{t.progress?.git_sha?.slice(0, 7) || '-'}</td>
            </tr>
          ))}
          {tasks.length === 0 && (
            <tr><td colSpan={5} className="tl-empty">No tasks match filter.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
