import { useState, useEffect } from 'react'
import './AlertsPanel.css'

interface Alert {
  id: string; level: string; message: string; task_id: string | null
  source: string; created_at: string
}

const LEVEL_COLORS: Record<string, string> = { error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' }

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [level, setLevel] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchAlerts = () => {
    setLoading(true)
    const params = level ? `?level=${level}` : ''
    fetch(`/api/alerts${params}`)
      .then(r => r.json())
      .then(d => setAlerts(d.alerts || []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchAlerts() }, [level])

  return (
    <div className="alerts-panel">
      <h2>Alerts</h2>
      <div className="ap-filters">
        {['', 'error', 'warning', 'info'].map(l => (
          <button key={l} className={level === l ? 'active' : ''} onClick={() => setLevel(l)}>
            {l || 'ALL'}
          </button>
        ))}
      </div>
      {loading ? <div className="ap-loading">Loading...</div> : (
        <table className="ap-table">
          <thead>
            <tr><th>Level</th><th>Message</th><th>Task</th><th>Source</th><th>Time</th></tr>
          </thead>
          <tbody>
            {alerts.map(a => (
              <tr key={a.id}>
                <td><span className="ap-level" style={{ background: LEVEL_COLORS[a.level] || '#6b7280' }}>{a.level}</span></td>
                <td>{a.message}</td>
                <td>{a.task_id || '-'}</td>
                <td>{a.source}</td>
                <td className="ap-time">{a.created_at?.slice(11, 19)}</td>
              </tr>
            ))}
            {alerts.length === 0 && <tr><td colSpan={5} className="ap-empty">No alerts.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  )
}
