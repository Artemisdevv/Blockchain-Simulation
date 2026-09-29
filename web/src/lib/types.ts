// Mirrors docs/API.md exactly - verified against the real running API.

export interface Transaction {
  id: string
  payload: number | unknown[]
  sender: string
  receiver: string
  ts: number
  sign?: string
}

export interface Stake {
  id: string
  staker: string
  amt: number
  ts: number
  sign?: string
}

export interface Block {
  id: string
  prevHash: string | null
  ts: number
  creator: string
  staked_amt: number
  files: Record<string, string>
  transactions: Transaction[]
  stakers: Stake[]
  vrf_proof_b64?: string
  seed?: string
  sign?: string
}

export interface Peer {
  host: string
  port: number
  name: string
  public_key: string
}

export interface StakersResponse {
  stakers: Record<string, number>
  epoch_ends_in_seconds: number
}

export interface BalanceResponse {
  public_key: string
  balance: number
}

export type ServerEvent =
  | { type: 'block_appended'; block: Block }
  | { type: 'peer_discovered'; peer: Peer }
  | { type: 'stake_registered'; staker: string; amount: number }
  | { type: 'node_slashed'; creator: string; block_pos: number }
