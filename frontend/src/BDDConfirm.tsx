import { useState, useEffect } from 'react'
import './BDDConfirm.css'

interface BDDStatus {
  req_id: string
  status: string
  bdd: { given: string; when: string; then: string } | null
  feedback: string | null
  confirmed_at: string | null
}

interface Props {
  reqId: string
  onClose: () => void
}

export default function BDDConfirm({ reqId, onClose }: Props) {
  const [bdd, setBdd] = useState<BDDStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [feedback, setFeedback] = useState('')
  const [given, setGiven] = useState('')
  const [when, setWhen] = useState('')
  const [then, setThen] = useState('')
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState('')

  const fetchBDD = () => {
    setLoading(true)
    fetch(`/api/bdd/${reqId}`)
      .then(r => r.json())
      .then(d => {
        setBdd(d)
        if (d.bdd) {
          setGiven(d.bdd.given || '')
          setWhen(d.bdd.when || '')
          setThen(d.bdd.then || '')
        }
      })
      .catch(() => setMsg('Failed to load BDD'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchBDD() }, [reqId])

  const confirm = async () => {
    setSending(true); setMsg('')
    try {
      const r = await fetch('/api/bdd/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ req_id: reqId, given, when, then, confirmed: true }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || 'Failed')
      setMsg('BDD confirmed!')
      fetchBDD()
    } catch (e: any) { setMsg(e.message) }
    finally { setSending(false) }
  }

  const sendFeedback = async () => {
    if (!feedback.trim()) return
    setSending(true); setMsg('')
    try {
      const r = await fetch('/api/bdd/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ req_id: reqId, feedback, given: given || null, when: when || null, then: then || null }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || 'Failed')
      setMsg('Feedback sent')
      setFeedback('')
      fetchBDD()
    } catch (e: any) { setMsg(e.message) }
    finally { setSending(false) }
  }

  if (loading) return <div className="bdd-panel"><div className="bdd-loading">Loading BDD...</div></div>

  const confirmed = bdd?.status === 'confirmed'

  return (
    <div className="bdd-panel">
      <div className="bdd-header">
        <h3>BDD — {reqId}</h3>
        <button className="bdd-close" onClick={onClose}>✕</button>
      </div>

      <div className="bdd-status-row">
        Status: <span className={`bdd-badge ${bdd?.status}`}>{bdd?.status || 'unknown'}</span>
      </div>

      <div className="bdd-fields">
        <label>Given</label>
        <textarea value={given} onChange={e => setGiven(e.target.value)} rows={2} disabled={confirmed} />
        <label>When</label>
        <textarea value={when} onChange={e => setWhen(e.target.value)} rows={2} disabled={confirmed} />
        <label>Then</label>
        <textarea value={then} onChange={e => setThen(e.target.value)} rows={2} disabled={confirmed} />
      </div>

      <div className="bdd-actions">
        {!confirmed && (
          <>
            <button className="bdd-btn confirm" onClick={confirm} disabled={sending}>
              {sending ? '...' : 'Confirm'}
            </button>
            <input
              className="bdd-feedback-input"
              placeholder="Feedback (reject or suggest changes)"
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
            />
            <button className="bdd-btn feedback" onClick={sendFeedback} disabled={sending || !feedback.trim()}>
              {sending ? '...' : 'Send Feedback'}
            </button>
          </>
        )}
        {confirmed && <div className="bdd-confirmed-msg">Confirmed at {bdd?.confirmed_at?.slice(0, 19)}</div>}
      </div>

      {msg && <div className="bdd-msg">{msg}</div>}
    </div>
  )
}
