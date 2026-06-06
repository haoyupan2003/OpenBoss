import { useState, useEffect } from 'react'
import BDDConfirm from './BDDConfirm'
import './RequirementForm.css'

interface Requirement {
  id: string
  title: string | null
  raw_need: string
  status: string
  created_at: string
}

export default function RequirementForm() {
  const [rawNeed, setRawNeed] = useState('')
  const [title, setTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<Requirement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [list, setList] = useState<Requirement[]>([])
  const [selectedReq, setSelectedReq] = useState<string | null>(null)

  const fetchList = () => {
    fetch('/api/requirements')
      .then(r => r.json())
      .then(d => setList(d.requirements || []))
      .catch(() => {})
  }

  useEffect(() => { fetchList() }, [])

  const handleSubmit = async () => {
    if (!rawNeed.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const r = await fetch('/api/requirements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_need: rawNeed, title: title || null }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || 'Failed')
      const data = await r.json()
      setResult(data)
      setRawNeed('')
      setTitle('')
      fetchList()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const STATUS_COLORS: Record<string, string> = {
    pending: '#f59e0b', processing: '#3b82f6', task_json_ready: '#22c55e', failed: '#ef4444',
    bdd_confirmed: '#8b5cf6', bdd_feedback_received: '#ec4899',
  }

  return (
    <div className="req-form">
      <h2>Submit Requirement</h2>

      <div className="rf-inputs">
        <input
          className="rf-title"
          placeholder="Title (optional)"
          value={title}
          onChange={e => setTitle(e.target.value)}
        />
        <textarea
          className="rf-need"
          placeholder="Describe your requirement in natural language..."
          rows={4}
          value={rawNeed}
          onChange={e => setRawNeed(e.target.value)}
        />
        <button className="rf-submit" onClick={handleSubmit} disabled={submitting || !rawNeed.trim()}>
          {submitting ? 'Submitting...' : 'Submit'}
        </button>
      </div>

      {error && <div className="rf-error">{error}</div>}
      {result && (
        <div className="rf-result">
          Requirement <code>{result.id}</code> submitted — status:&nbsp;
          <span className="rf-status" style={{ background: STATUS_COLORS[result.status] || '#6b7280' }}>
            {result.status}
          </span>
        </div>
      )}

      <h3 className="rf-list-h">Submitted ({list.length})</h3>
      <table className="rf-table">
        <thead>
          <tr><th>ID</th><th>Title</th><th>Status</th></tr>
        </thead>
        <tbody>
          {list.map(r => (
            <tr key={r.id} className={selectedReq === r.id ? 'rf-selected' : ''}
                onClick={() => setSelectedReq(selectedReq === r.id ? null : r.id)}
                style={{ cursor: 'pointer' }}>
              <td className="rf-id">{r.id}</td>
              <td>{r.title || r.raw_need?.slice(0, 50) || '-'}</td>
              <td>
                <span className="rf-status" style={{ background: STATUS_COLORS[r.status] || '#6b7280' }}>
                  {r.status}
                </span>
              </td>
            </tr>
          ))}
          {list.length === 0 && <tr><td colSpan={3} className="rf-empty">No requirements yet.</td></tr>}
        </tbody>
      </table>

      {selectedReq && <BDDConfirm reqId={selectedReq} onClose={() => setSelectedReq(null)} />}
    </div>
  )
}
