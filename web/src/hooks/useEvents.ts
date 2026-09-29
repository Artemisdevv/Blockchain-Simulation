import { useEffect, useRef } from 'react'
import { eventsUrlFor, type Connection } from '@/lib/connection'
import type { ServerEvent } from '@/lib/types'

// Reconnects with backoff rather than giving up - a demo shouldn't die
// because one packet got dropped. Capped at 10s so it doesn't hammer a
// genuinely-down peer forever either.
export function useEvents(conn: Connection | null, onEvent: (event: ServerEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!conn) return

    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let closedByCleanup = false
    let attempt = 0

    function connect() {
      socket = new WebSocket(eventsUrlFor(conn!.apiUrl, conn!.token))

      socket.onmessage = (msg) => {
        try {
          const parsed: ServerEvent = JSON.parse(msg.data)
          onEventRef.current(parsed)
        } catch {
          // ignore malformed frames rather than crash the whole dashboard
        }
      }

      socket.onopen = () => {
        attempt = 0
      }

      socket.onclose = () => {
        if (closedByCleanup) return
        const delay = Math.min(10_000, 500 * 2 ** attempt)
        attempt += 1
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closedByCleanup = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [conn])
}
