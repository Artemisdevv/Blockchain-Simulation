import type { BalanceResponse, Block, Peer, StakersResponse, Transaction } from './types'
import type { Connection } from './connection'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(conn: Connection, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${conn.apiUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${conn.token}`,
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  const body = await res.json().catch(() => ({}))

  if (!res.ok) {
    const message =
      res.status === 429
        ? (body.error ?? 'Rate limited - back off and retry shortly')
        : (body.error ?? `Request failed (${res.status})`)
    throw new ApiError(res.status, message)
  }

  return body as T
}

export const api = {
  getChain: (conn: Connection) => request<{ blocks: Block[] }>(conn, '/chain'),
  getPeers: (conn: Connection) => request<{ peers: Peer[] }>(conn, '/peers'),
  getMempool: (conn: Connection) => request<{ transactions: Transaction[] }>(conn, '/mempool'),
  getStakers: (conn: Connection) => request<StakersResponse>(conn, '/stakers'),
  getBalance: (conn: Connection) => request<BalanceResponse>(conn, '/balance'),

  sendTransaction: (conn: Connection, receiver: string, amount: number) =>
    request<{ ok: boolean; transaction_id: string | null }>(conn, '/transactions', {
      method: 'POST',
      body: JSON.stringify({ receiver, amount }),
    }),

  stake: (conn: Connection, amount: number) =>
    request<{ ok: boolean; creating_block_in_seconds?: number; error?: string }>(conn, '/stakes', {
      method: 'POST',
      body: JSON.stringify({ amount }),
    }),
}
