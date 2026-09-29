import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '@/lib/api'
import type { Connection } from '@/lib/connection'
import type { Block, Peer, ServerEvent, Transaction } from '@/lib/types'
import { useEvents } from './useEvents'

export interface SlashEvent {
  creator: string
  blockPos: number
  at: number
}

interface NetworkState {
  blocks: Block[]
  peers: Peer[]
  mempool: Transaction[]
  stakers: Record<string, number>
  epochEndsInSeconds: number
  myPublicKey: string | null
  myBalance: number | null
  connected: boolean
  error: string | null
  lastSlash: SlashEvent | null
}

const POLL_INTERVAL_MS = 5000 // fallback only - /events covers most updates live

export function useNetworkState(conn: Connection | null) {
  const [state, setState] = useState<NetworkState>({
    blocks: [],
    peers: [],
    mempool: [],
    stakers: {},
    epochEndsInSeconds: 0,
    myPublicKey: null,
    myBalance: null,
    connected: false,
    error: null,
    lastSlash: null,
  })

  const refresh = useCallback(async () => {
    if (!conn) return
    try {
      const [chain, peers, mempool, stakers, balance] = await Promise.all([
        api.getChain(conn),
        api.getPeers(conn),
        api.getMempool(conn),
        api.getStakers(conn),
        api.getBalance(conn),
      ])
      setState((s) => ({
        ...s,
        blocks: chain.blocks,
        peers: peers.peers,
        mempool: mempool.transactions,
        stakers: stakers.stakers,
        epochEndsInSeconds: stakers.epoch_ends_in_seconds,
        myPublicKey: balance.public_key,
        myBalance: balance.balance,
        connected: true,
        error: null,
      }))
    } catch (e) {
      setState((s) => ({
        ...s,
        connected: false,
        error: e instanceof ApiError ? e.message : 'Could not reach the node',
      }))
    }
  }, [conn])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [refresh])

  useEvents(conn, (event: ServerEvent) => {
    setState((s) => {
      switch (event.type) {
        case 'block_appended':
          if (s.blocks.some((b) => b.id === event.block.id)) return s
          return { ...s, blocks: [...s.blocks, event.block] }
        case 'peer_discovered':
          if (s.peers.some((p) => p.public_key === event.peer.public_key)) return s
          return { ...s, peers: [...s.peers, event.peer] }
        case 'stake_registered':
          return { ...s, stakers: { ...s.stakers, [event.staker]: event.amount } }
        case 'node_slashed':
          return { ...s, lastSlash: { creator: event.creator, blockPos: event.block_pos, at: Date.now() } }
        default:
          return s
      }
    })
  })

  // Epoch countdown ticks locally between polls, corrected by each /stakers refresh
  useEffect(() => {
    const tick = setInterval(() => {
      setState((s) => (s.epochEndsInSeconds > 0 ? { ...s, epochEndsInSeconds: s.epochEndsInSeconds - 1 } : s))
    }, 1000)
    return () => clearInterval(tick)
  }, [])

  return { state, refresh }
}
