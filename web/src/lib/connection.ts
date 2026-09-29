// Connection config (API URL + token) is per-viewer, not shared state -
// localStorage is the right tool here, not a backend call. See docs/API.md
// for why the token exists at all (it's not a user login).

export interface Connection {
  apiUrl: string
  token: string
}

const STORAGE_KEY = 'blocksim.connection'

export function loadConnection(): Connection | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed.apiUrl === 'string' && typeof parsed.token === 'string') {
      return parsed
    }
    return null
  } catch {
    return null
  }
}

export function saveConnection(conn: Connection): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conn))
  } catch {
    // best-effort only - a private window or blocked storage just means
    // the viewer re-enters connection details next time, not a hard failure
  }
}

export function clearConnection(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

// The events websocket runs on apiUrl's port + 1 (see webapi/events.py)
export function eventsUrlFor(apiUrl: string, token: string): string {
  const url = new URL(apiUrl)
  const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  const eventsPort = Number(url.port || (url.protocol === 'https:' ? 443 : 80)) + 1
  return `${wsProtocol}//${url.hostname}:${eventsPort}/events?token=${encodeURIComponent(token)}`
}
