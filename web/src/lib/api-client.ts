import type {
  ChainResponse,
  MempoolResponse,
  PeersResponse,
  StakeResponse,
  StakersResponse,
  TransactionResponse,
  BalanceResponse,
  NodeSlashedEvent,
} from "@/features/blockchain/mock-data";

export interface Connection {
  url: string;
  token: string;
  wsUrl?: string | undefined;
  readOnly?: boolean;
}

export type PeerRole = "honest" | "malicious";

export interface RoomPeerRequest {
  name: string;
  room_id: string;
  role?: PeerRole;
}

export interface RoomPeerResponse {
  peer_id: string;
  name: string;
  room_id: string;
  role?: PeerRole;
  token: string;
}

export async function startRoomPeer(config: RoomPeerRequest): Promise<RoomPeerResponse> {
  const response = await fetch("/api/peer-setup/peers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    let message = `HTTP ${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data?.error) message = data.error;
    } catch {
      // Keep the HTTP error when the manager response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<RoomPeerResponse>;
}

/**
 * Peer id of a connection created through the peer manager, or null for demo
 * peers and spectator URLs (which have nothing to stop).
 */
export function peerIdFromConnection(connection: Connection): string | null {
  const match = /^\/api\/runtime\/([0-9a-f]+)$/.exec(connection.url);
  return match ? (match[1] ?? null) : null;
}

const PEER_GONE_MESSAGE = "Peer is no longer running.";

/** The peer manager no longer has this peer (restarted, idle-reaped, or stopped). */
export class PeerGoneError extends Error {
  constructor() {
    super(PEER_GONE_MESSAGE);
    this.name = "PeerGoneError";
  }
}

/** `token` must belong to a live peer in the same room as `peerId` (usually your own connection's). */
export async function stopRoomPeer(peerId: string, token: string): Promise<void> {
  const response = await fetch(`/api/peer-setup/peers/${encodeURIComponent(peerId)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Failed to stop managed peer (HTTP ${response.status}).`);
  }
}

export interface ManagedPeerSummary {
  peer_id: string;
  name: string;
  room_id: string;
  role?: PeerRole;
}

export async function listManagedPeers(): Promise<ManagedPeerSummary[]> {
  const response = await fetch("/api/peer-setup/peers");
  if (!response.ok) throw new Error(`Failed to load managed peers (HTTP ${response.status}).`);
  const data = (await response.json()) as { peers: ManagedPeerSummary[] };
  return data.peers;
}

/** Read-only link for the room `peerToken` belongs to; the server derives the room from the token. */
export async function createSpectatorLink(peerToken: string): Promise<string> {
  const response = await fetch("/api/peer-setup/spectator-links", {
    method: "POST",
    headers: { Authorization: `Bearer ${peerToken}` },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error || `Unable to create spectator link (HTTP ${response.status}).`);
  const url = new URL(window.location.origin);
  url.searchParams.set("mode", "spectator");
  url.searchParams.set("room", data.room_id);
  url.searchParams.set("spectatorToken", data.spectator_token);
  return url.toString();
}

export async function downloadRunReport(connection: Connection): Promise<void> {
  const baseUrl = connection.url.replace(/\/+$/, "");
  const response = await fetch(`${baseUrl}/report.pdf`, {
    headers: { Authorization: `Bearer ${connection.token}` },
  });
  if (!response.ok) throw new Error(`Could not export the run report (HTTP ${response.status}).`);
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = "blockchain-run-report.pdf";
  anchor.click();
  URL.revokeObjectURL(href);
}

export async function apiRequest<T>(
  connection: Connection,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const baseUrl = connection.url.replace(/\/+$/, "");
  const res = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${connection.token}`,
      ...options.headers,
    },
  });

  if (!res.ok) {
    let errorMessage = `HTTP ${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (data && data.error) errorMessage = data.error;
    } catch {
      // Ignore JSON parse error
    }
    if (res.status === 404 && errorMessage === PEER_GONE_MESSAGE) throw new PeerGoneError();
    throw new Error(errorMessage);
  }

  return res.json() as Promise<T>;
}

export async function fetchChain(connection: Connection): Promise<ChainResponse> {
  return apiRequest<ChainResponse>(connection, "/chain");
}

export async function fetchPeers(connection: Connection): Promise<PeersResponse> {
  return apiRequest<PeersResponse>(connection, "/peers");
}

export async function fetchMempool(connection: Connection): Promise<MempoolResponse> {
  return apiRequest<MempoolResponse>(connection, "/mempool");
}

export async function fetchStakers(connection: Connection): Promise<StakersResponse> {
  return apiRequest<StakersResponse>(connection, "/stakers");
}

export async function fetchBalance(connection: Connection): Promise<BalanceResponse> {
  return apiRequest<BalanceResponse>(connection, "/balance");
}

export interface InvariantsResponse {
  honest_consensus: boolean;
  supply_conserved: boolean;
  valid_proposers: boolean;
  total_blocks: number;
  mempool_count: number;
  peer_count: number;
}

export async function fetchInvariants(connection: Connection): Promise<InvariantsResponse> {
  return apiRequest<InvariantsResponse>(connection, "/invariants");
}

export interface TriggerAttackResponse {
  ok: boolean;
  attack: string;
  target_block_pos?: number;
  message: string;
  error?: string;
}

export interface MetricsResponse {
  blocks_count: number;
  total_transactions: number;
  total_staked: number;
  mempool_count: number;
  peer_count: number;
  avg_block_time_sec: number;
  room_id: string;
}

export async function fetchMetrics(connection: Connection): Promise<MetricsResponse> {
  return apiRequest<MetricsResponse>(connection, "/metrics");
}

export async function triggerAttack(
  connection: Connection,
  attackType = "double_sign",
): Promise<TriggerAttackResponse> {
  return apiRequest<TriggerAttackResponse>(connection, "/malicious/trigger", {
    method: "POST",
    body: JSON.stringify({ attack_type: attackType }),
  });
}

export interface AttackLabState {
  blocked_peers: string[];
  latency_ms: number;
  censored_receivers: string[];
}

export async function fetchAttackLabState(connection: Connection): Promise<AttackLabState> {
  return apiRequest<AttackLabState>(connection, "/attack-lab/state");
}

export async function setPeerPartition(connection: Connection, peerKeys: string[]) {
  return apiRequest<{ ok: boolean }>(connection, "/attack-lab/partition", {
    method: "POST", body: JSON.stringify({ peer_keys: peerKeys }),
  });
}

export async function healPeerPartition(connection: Connection) {
  return apiRequest<{ ok: boolean }>(connection, "/attack-lab/heal-partition", { method: "POST", body: "{}" });
}

export async function setPeerLatency(connection: Connection, latencyMs: number) {
  return apiRequest<{ ok: boolean; latency_ms: number }>(connection, "/attack-lab/latency", {
    method: "POST", body: JSON.stringify({ latency_ms: latencyMs }),
  });
}

export async function setPeerCensorship(connection: Connection, receiver: string, enabled: boolean) {
  return apiRequest<{ ok: boolean }>(connection, "/attack-lab/censorship", {
    method: "POST", body: JSON.stringify({ receiver, enabled }),
  });
}

export async function submitTransaction(
  connection: Connection,
  receiver: string,
  amount: number,
): Promise<TransactionResponse> {
  return apiRequest<TransactionResponse>(connection, "/transactions", {
    method: "POST",
    body: JSON.stringify({ receiver, amount }),
  });
}

export async function submitStake(
  connection: Connection,
  amount: number,
): Promise<StakeResponse> {
  return apiRequest<StakeResponse>(connection, "/stakes", {
    method: "POST",
    body: JSON.stringify({ amount }),
  });
}

export interface FaucetResponse {
  ok: boolean;
  added_amount: number;
  new_balance: number;
  transaction_id?: string;
  error?: string;
}

export async function requestFaucet(
  connection: Connection,
  amount = 50,
): Promise<FaucetResponse> {
  return apiRequest<FaucetResponse>(connection, "/faucet", {
    method: "POST",
    body: JSON.stringify({ amount }),
  });
}

export interface AutoStakeResponse {
  enabled: boolean;
  available: boolean;
}

export async function fetchAutoStake(connection: Connection): Promise<AutoStakeResponse> {
  return apiRequest<AutoStakeResponse>(connection, "/auto_stake");
}

export async function setAutoStake(
  connection: Connection,
  enabled: boolean,
): Promise<AutoStakeResponse> {
  return apiRequest<AutoStakeResponse>(connection, "/auto_stake", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export interface WsEventHandlers {
  onBlockAppended?: (block: any) => void;
  onPeerDiscovered?: (peer: any) => void;
  onPeerLeft?: (peer: any) => void;
  onStakeRegistered?: (data: { staker: string; amount: number }) => void;
  onNodeSlashed?: (event: NodeSlashedEvent) => void;
  onAttackState?: (event: Record<string, unknown>) => void;
  onOpen?: () => void;
  onError?: (err: Event) => void;
  onClose?: () => void;
}

export function connectEventsWs(
  connection: Connection,
  handlers: WsEventHandlers,
): () => void {
  try {
    const url = new URL(connection.wsUrl || connection.url, window.location.href);
    if (window.location.protocol === "https:" && (url.protocol === "http:" || url.protocol === "ws:")) {
      url.protocol = "wss:";
    } else if (window.location.protocol !== "https:" && url.protocol === "http:") {
      url.protocol = "ws:";
    }
    if (!connection.wsUrl) {
      const proxyRoute = url.pathname.match(/^\/api\/([^/]+)(?:\/|$)/);
      if (proxyRoute) {
        url.pathname = `/ws/${proxyRoute[1]}/events`;
      } else {
        const restPort = url.port;
        // Keep the same origin's default 80/443 port for tunneled URLs. When
        // the REST URL has an explicit port (as in local Compose), retain the
        // established port+1 convention for the events socket.
        url.port = restPort ? String(parseInt(restPort, 10) + 1) : "";
        url.pathname = "/events";
      }
    }
    url.searchParams.set("token", connection.token);
    const wsUrl = url.toString();

    let ws: WebSocket | null = null;
    let active = true;
    let retry = 0;
    let timer = 0;
    const connect = () => {
      if (!active) return;
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        retry = 0;
        handlers.onOpen?.();
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!data || !data.type) return;

          switch (data.type) {
          case "block_appended":
            handlers.onBlockAppended?.(data.block);
            break;
          case "peer_discovered":
            handlers.onPeerDiscovered?.(data.peer);
            break;
          case "peer_left":
            handlers.onPeerLeft?.(data.peer);
            break;
          case "stake_registered":
            handlers.onStakeRegistered?.(data);
            break;
          case "node_slashed":
            handlers.onNodeSlashed?.({
              type: "node_slashed",
              creator: data.creator,
              block_pos: data.block_pos,
            });
            break;
          case "attack_state":
            handlers.onAttackState?.(data);
            break;
          }
        } catch (err) {
          console.error("Failed to parse WS message:", err);
        }
      };
      ws.onerror = (err) => handlers.onError?.(err);
      ws.onclose = () => {
        handlers.onClose?.();
        if (active) {
          const delay = Math.min(30000, 1000 * 2 ** retry++);
          timer = window.setTimeout(connect, delay);
        }
      };
    };
    connect();

    return () => {
      active = false;
      window.clearTimeout(timer);
      ws?.close();
    };
  } catch (err) {
    console.error("Failed to initialize WebSocket:", err);
    return () => {};
  }
}
