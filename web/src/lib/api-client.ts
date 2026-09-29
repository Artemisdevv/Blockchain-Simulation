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

export interface WsEventHandlers {
  onBlockAppended?: (block: any) => void;
  onPeerDiscovered?: (peer: any) => void;
  onStakeRegistered?: (data: { staker: string; amount: number }) => void;
  onNodeSlashed?: (event: NodeSlashedEvent) => void;
  onOpen?: () => void;
  onError?: (err: Event) => void;
  onClose?: () => void;
}

export function connectEventsWs(
  connection: Connection,
  handlers: WsEventHandlers,
): () => void {
  try {
    const url = new URL(connection.url);
    const wsProtocol = url.protocol === "https:" ? "wss:" : "ws:";
    const restPort = url.port ? parseInt(url.port, 10) : 80;
    const wsPort = restPort + 1;
    const wsUrl = `${wsProtocol}//${url.hostname}:${wsPort}/events?token=${encodeURIComponent(
      connection.token,
    )}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
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
        }
      } catch (err) {
        console.error("Failed to parse WS message:", err);
      }
    };

    ws.onerror = (err) => {
      handlers.onError?.(err);
    };

    ws.onclose = () => {
      handlers.onClose?.();
    };

    return () => {
      ws.close();
    };
  } catch (err) {
    console.error("Failed to initialize WebSocket:", err);
    return () => {};
  }
}
