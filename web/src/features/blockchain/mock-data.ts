export interface Transaction {
  id: string;
  payload: number;
  sender: string;
  receiver: string;
  ts: number;
  sign?: string;
}
export interface Stake {
  id: string;
  staker: string;
  amt: number;
  ts: number;
  sign: string;
}
export interface Block {
  id: string;
  prevHash: string | null;
  ts: number;
  creator: string;
  staked_amt: number;
  files: Record<string, unknown>;
  transactions: Transaction[];
  stakers: Stake[];
  vrf_proof_b64: string;
  seed: string;
  sign: string;
}
export interface Peer {
  host: string;
  port: number;
  name: string;
  public_key: string;
}
export interface ChainResponse {
  blocks: Block[];
}
export interface PeersResponse {
  peers: Peer[];
}
export interface MempoolResponse {
  transactions: Transaction[];
}
export interface StakersResponse {
  stakers: Record<string, number>;
  epoch_ends_in_seconds: number;
}
export interface BalanceResponse {
  public_key: string;
  balance: number;
}
export interface TransactionResponse {
  ok: true;
  transaction_id: string;
}
export type StakeResponse =
  { ok: true; creating_block_in_seconds: number } | { ok: false; error: string };
export interface NodeSlashedEvent {
  type: "node_slashed";
  creator: string;
  block_pos: number;
}

const pem = (name: string, suffix: string) =>
  `-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA${name.toUpperCase()}${suffix}8r4K9xQ2wL7pN3mZ0=\n-----END PUBLIC KEY-----`;
export const keys = {
  self: pem("alpha", "7G2K5M9P1Q4R6S8T"),
  bob: pem("bob", "2F8H4J6L0N3V5X7Z"),
  carol: pem("carol", "9B1D3F5H7J2L4N6P"),
  mallory: pem("mallory", "6C8E0G2I4K7M9O1Q"),
};

const transactionOne: Transaction = {
  id: "tx-8f14e45f-ea71-4a11",
  payload: 12,
  sender: keys.bob,
  receiver: keys.self,
  ts: 1770031924.2,
  sign: "MEUCIQDQ8rWv4mQv9nX0YyZ6c7aR...",
};
const transactionTwo: Transaction = {
  id: "tx-c9f0f895-fb98-4b03",
  payload: 8,
  sender: keys.self,
  receiver: keys.carol,
  ts: 1770031978.8,
  sign: "MEQCIDp2V4yH7mN9qT1wK5zA...",
};
const transactionThree: Transaction = {
  id: "tx-45c48cce-2e2d-4d61",
  payload: 5,
  sender: keys.carol,
  receiver: keys.bob,
  ts: 1770032040.1,
  sign: "MEYCIQC3kP7sR1xV5zB9dF2h...",
};

export const initialMockData = {
  chain: {
    blocks: [
      {
        id: "blk-0001-genesis",
        prevHash: null,
        ts: 1770031020000,
        creator: keys.bob,
        staked_amt: 18,
        files: {},
        transactions: [transactionOne],
        stakers: [
          {
            id: "stk-a91e",
            staker: keys.bob,
            amt: 18,
            ts: 1770030990.2,
            sign: "MEUCIFirstStakeSignature...",
          },
        ],
        vrf_proof_b64: "eyJwcm9vZiI6ImdlbmVzaXMifQ==",
        seed: "2de8396fe3d91c8a79a46e423d0c02ad",
        sign: "MEUCIQDGenesisBlockSignature...",
      },
      {
        id: "blk-0002-a58c",
        prevHash: "2de8396fe3d91c8a79a46e423d0c02ad",
        ts: 1770031620000,
        creator: keys.self,
        staked_amt: 42,
        files: {},
        transactions: [transactionTwo],
        stakers: [
          {
            id: "stk-b27f",
            staker: keys.self,
            amt: 42,
            ts: 1770031588.4,
            sign: "MEUCIAlphaStakeSignature...",
          },
        ],
        vrf_proof_b64: "eyJwcm9vZiI6ImFscGhhLXdpbiJ9",
        seed: "9f86d081884c7d659a2feaa0c55ad015",
        sign: "MEUCIQDAlphaBlockSignature...",
      },
      {
        id: "blk-0003-f19d",
        prevHash: "9f86d081884c7d659a2feaa0c55ad015",
        ts: 1770032220000,
        creator: keys.carol,
        staked_amt: 25,
        files: {},
        transactions: [transactionThree],
        stakers: [
          {
            id: "stk-c84a",
            staker: keys.carol,
            amt: 25,
            ts: 1770032186.6,
            sign: "MEUCICarolStakeSignature...",
          },
        ],
        vrf_proof_b64: "eyJwcm9vZiI6ImNhcm9sLXdpbiJ9",
        seed: "6b51d431df5d7f141cbececcf79edf3d",
        sign: "MEUCIQDCarolBlockSignature...",
      },
      {
        id: "blk-0004-7de1",
        prevHash: "6b51d431df5d7f141cbececcf79edf3d",
        ts: 1770032820000,
        creator: keys.mallory,
        staked_amt: 0,
        files: {},
        transactions: [],
        stakers: [],
        vrf_proof_b64: "eyJwcm9vZiI6ImludmFsaWQifQ==",
        seed: "d4735e3a265e16eee03f59718b9b5d03",
        sign: "MEUCIQDMalloryDoubleSignEvidence...",
      },
    ],
  } satisfies ChainResponse,
  peers: {
    peers: [
      { host: "127.0.0.1", port: 5000, name: "alpha-node", public_key: keys.self },
      { host: "localhost", port: 5001, name: "bob", public_key: keys.bob },
      { host: "localhost", port: 5002, name: "carol", public_key: keys.carol },
      { host: "10.0.0.24", port: 5003, name: "mallory", public_key: keys.mallory },
    ],
  } satisfies PeersResponse,
  mempool: {
    transactions: [
      {
        id: "tx-d3d94468-2a44-4c42",
        payload: 3,
        sender: keys.bob,
        receiver: keys.self,
        ts: 1770033004.3,
      },
      {
        id: "tx-6512bd43-909f-44c1",
        payload: 14,
        sender: keys.self,
        receiver: keys.carol,
        ts: 1770033018.7,
      },
      {
        id: "tx-c20ad4d7-bd11-4fe9",
        payload: 2,
        sender: keys.carol,
        receiver: keys.bob,
        ts: 1770033033.1,
      },
    ],
  } satisfies MempoolResponse,
  stakers: {
    stakers: { [keys.self]: 42, [keys.bob]: 18, [keys.carol]: 25, [keys.mallory]: 0 },
    epoch_ends_in_seconds: 34,
  } satisfies StakersResponse,
  balance: { public_key: keys.self, balance: 145 } satisfies BalanceResponse,
  slashed: { type: "node_slashed", creator: keys.mallory, block_pos: 3 } satisfies NodeSlashedEvent,
};

export const mockPresentation = {
  peerStatuses: {
    "alpha-node": "online",
    bob: "online",
    carol: "offline",
    mallory: "malicious",
  } as const,
  namesByKey: {
    [keys.self]: "alpha-node",
    [keys.bob]: "bob",
    [keys.carol]: "carol",
    [keys.mallory]: "mallory",
  } as Record<string, string>,
};
