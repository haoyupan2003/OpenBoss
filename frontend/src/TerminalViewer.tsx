import { useState, useEffect } from 'react'
import './TerminalViewer.css'

interface Props {
  agentId: string
}

export default function TerminalViewer({ agentId }: Props) {
  const [lines, setLines] = useState<string[]>([])
  const [available, setAvailable] = useState<boolean | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!expanded) return
    let cancelled = false
    const fetchTerminal = () => {
      fetch(`/api/terminal/${agentId}?lines=30`)
        .then(r => r.json())
        .then(d => { if (!cancelled) { setLines(d.output || []); setAvailable(d.available) } })
        .catch(() => { if (!cancelled) setAvailable(false) })
    }
    fetchTerminal()
    const timer = setInterval(fetchTerminal, 3000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [agentId, expanded])

  if (!expanded) {
    return <button className="tv-toggle" onClick={() => setExpanded(true)}>▶ Terminal</button>
  }

  return (
    <div className="tv-panel">
      <div className="tv-header">
        <span>Terminal — {agentId}</span>
        <button className="tv-close" onClick={() => setExpanded(false)}>✕</button>
      </div>
      {available === false && <div className="tv-offline">tmux not available</div>}
      <pre className="tv-output">{lines.join('\n') || '(empty)'}</pre>
    </div>
  )
}
