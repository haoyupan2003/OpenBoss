import { useEffect, useRef, useState } from 'react'

interface UseWebSocketResult {
  connected: boolean
  lastMessage: string | null
  send: (data: string) => void
}

export function useWebSocket(url: string = '/ws'): UseWebSocketResult {
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const fullUrl = url.startsWith('ws') ? url : `${protocol}//${window.location.host}${url}`
      const ws = new WebSocket(fullUrl)
      wsRef.current = ws

      ws.onopen = () => { if (!cancelled) setConnected(true) }
      ws.onclose = () => {
        if (!cancelled) setConnected(false)
      }
      ws.onerror = () => { ws.close() }
      ws.onmessage = (e) => { if (!cancelled) setLastMessage(e.data) }
    }

    connect()
    return () => {
      cancelled = true
      wsRef.current?.close()
    }
  }, [url])

  const send = (data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(data)
  }

  return { connected, lastMessage, send }
}
