import { useEffect, useState, useCallback, useRef } from "react";
import {
  Activity,
  Download,
  AlertTriangle,
  ArrowRight,
  Blocks,
  ChevronRight,
  Clock3,
  Coins,
  Database,
  GraduationCap,
  LogOut,
  Menu,
  Network,
  Radio,
  Send,
  Server,
  ShieldCheck,
  Users,
  WalletCards,
  X,
  Wifi,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { BlockDialog, TransactionDialog } from "./DetailDialog";
import { CopyValue, formatTime, normKey, shortKey } from "./utils";
import { SpectatorShare } from "./SpectatorShare";
import { ElectionExplainer } from "./ElectionExplainer";
import { Tutorial } from "./Tutorial";
import {
  connectEventsWs,
  fetchAttackLabState,
  fetchBalance,
  fetchChain,
  fetchInvariants,
  fetchMetrics,
  fetchMempool,
  fetchPeers,
  fetchStakers,
  fetchAutoStake,
  setAutoStake,
  downloadRunReport,
  healPeerPartition,
  listManagedPeers,
  requestFaucet,
  setPeerCensorship,
  setPeerLatency,
  setPeerPartition,
  stopRoomPeer,
  submitStake,
  submitTransaction,
  PeerGoneError,
  type Connection,
  type InvariantsResponse,
  type AttackLabState,
  type MetricsResponse,
  type ManagedPeerSummary,
} from "@/lib/api-client";
import type {
  Block,
  ChainResponse,
  MempoolResponse,
  NodeSlashedEvent,
  Peer,
  PeersResponse,
  StakersResponse,
  Transaction,
  BalanceResponse,
} from "./mock-data";

type View = "overview" | "explorer" | "network" | "validators" | "mempool" | "attack_lab";

const nav: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "explorer", label: "Explorer", icon: Blocks },
  { id: "network", label: "Network", icon: Network },
  { id: "validators", label: "Validators", icon: ShieldCheck },
  { id: "mempool", label: "Mempool", icon: Database },
  { id: "attack_lab", label: "Attack Lab", icon: AlertTriangle },
];

export function Dashboard({
  connection,
  onDisconnect,
}: {
  connection: Connection;
  onDisconnect: () => void;
}) {
  const [view, setView] = useState<View>("overview");
  const [mobileOpen, setMobileOpen] = useState(false);

  // Live state from container
  const [chain, setChain] = useState<ChainResponse>({ blocks: [] });
  const [peers, setPeers] = useState<PeersResponse>({ peers: [] });
  // Live "packets" for the network animation: one entry per tx / stake / block event.
  const [packets, setPackets] = useState<Packet[]>([]);
  const packetSeq = useRef(0);
  const addPacket = useCallback((kind: PacketKind, fromKey?: string) => {
    if (!fromKey) return;
    const id = ++packetSeq.current;
    setPackets((current) => [...current.slice(-40), { id, kind, fromKey }]);
    window.setTimeout(() => setPackets((current) => current.filter((p) => p.id !== id)), 2600);
  }, []);
  const [autoStake, setAutoStakeState] = useState<{ enabled: boolean; available: boolean }>({
    enabled: false,
    available: false,
  });
  const [mempool, setMempool] = useState<MempoolResponse>({ transactions: [] });
  const [stakers, setStakers] = useState<StakersResponse>({
    stakers: {},
    epoch_ends_in_seconds: 0,
  });
  const [balance, setBalance] = useState<BalanceResponse>({ public_key: "", balance: 0 });
  const [invariants, setInvariants] = useState<InvariantsResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [slashed, setSlashed] = useState<NodeSlashedEvent | null>(null);

  const [countdown, setCountdown] = useState(0);
  const [selectedBlock, setSelectedBlock] = useState<Block | null>(null);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [toast, setToast] = useState("");
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [wsConnected, setWsConnected] = useState(false);

  // Spectator mode detection
  const isSpectator = connection.readOnly === true;
  const [attackEvent, setAttackEvent] = useState<any>(null);
  const refreshAll = useCallback(async () => {
    try {
      const [c, p, m, s, b, inv, met] = await Promise.all([
        fetchChain(connection),
        fetchPeers(connection),
        fetchMempool(connection),
        fetchStakers(connection),
        isSpectator ? Promise.resolve({ public_key: "", balance: 0, pending_income: 0 }) : fetchBalance(connection),
        fetchInvariants(connection).catch(() => null),
        fetchMetrics(connection).catch(() => null),
      ]);
      setChain(c);
      setPeers(p);
      setMempool(m);
      setStakers(s);
      setBalance(b);
      if (inv) setInvariants(inv);
      if (met) setMetrics(met);
      setCountdown(s.epoch_ends_in_seconds);
      setLastUpdate(new Date());
    } catch (err: any) {
      if (err instanceof PeerGoneError) {
        // The peer process is gone (manager restarted, idle-reaped). Don't sit on a
        // dashboard of zeros: go back to the join screen so the user can rejoin.
        onDisconnect();
        return;
      }
      console.error("Failed to fetch node state:", err);
    }
  }, [connection, isSpectator, onDisconnect]);

  // Initial load & lightweight background refresh (30s cadence since WebSocket streams live updates)
  useEffect(() => {
    refreshAll();
    const interval = window.setInterval(refreshAll, 30000);
    return () => window.clearInterval(interval);
  }, [refreshAll]);

  useEffect(() => {
    fetchAutoStake(connection)
      .then(setAutoStakeState)
      .catch(() => setAutoStakeState({ enabled: false, available: false }));
  }, [connection]);

  const toggleAutoStake = async (enabled: boolean) => {
    try {
      const res = await setAutoStake(connection, enabled);
      setAutoStakeState({ enabled: res.enabled, available: res.available });
      setToast(enabled ? "Auto-stake on: this node stakes each epoch." : "Auto-stake off: stake manually.");
    } catch (err: any) {
      setToast(err.message || "Failed to change auto-stake.");
    }
  };

  // WebSocket Live Events
  useEffect(() => {
    const unsubscribe = connectEventsWs(connection, {
      onOpen: () => setWsConnected(true),
      onClose: () => setWsConnected(false),
      onError: () => setWsConnected(false),
      onBlockAppended: (block) => {
        setToast("New block appended to chain!");
        addPacket("block", block?.creator);
        refreshAll();
      },
      onTxSeen: (tx) => {
        // Faucet mints come from "Genesis": show them arriving at the receiver instead.
        addPacket("tx", tx.sender === "Genesis" ? tx.receiver : tx.sender);
      },
      onPeerDiscovered: (peer) => {
        setToast(`Peer discovered: ${peer.name || peer.host}`);
        fetchPeers(connection).then(setPeers);
      },
      onPeerLeft: (peer) => {
        setToast(`Peer left: ${peer.name || peer.host}`);
        fetchPeers(connection).then(setPeers);
      },
      onStakeRegistered: (data) => {
        setToast(`Stake registered: ${data.amount} coins`);
        addPacket("stake", data.staker);
        fetchStakers(connection).then((s) => {
          setStakers(s);
          setCountdown(s.epoch_ends_in_seconds);
        });
      },
      onNodeSlashed: (event) => {
        setSlashed(event);
        setToast(`MALICIOUS ACTIVITY DETECTED: Validator slashed!`);
        refreshAll();
      },
      onAttackState: (event) => setAttackEvent(event),
    });

    return () => unsubscribe();
  }, [connection, refreshAll, addPacket]);

  // Countdown timer decrement
  useEffect(() => {
    const timer = window.setInterval(() => {
      setCountdown((v) => (v <= 1 ? 0 : v - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  // Toast dismissal
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  // Helper to map public keys to names
  const getName = useCallback(
    (pubkey: string): string => {
      if (!pubkey) return "Unknown";
      const cleanPubkey = normKey(pubkey);
      const cleanSelf = balance.public_key ? normKey(balance.public_key) : "";
      if (cleanSelf && cleanPubkey === cleanSelf) return "You";
      if (pubkey === "Genesis") return "Genesis";
      const match = peers.peers.find((p) => p.public_key && normKey(p.public_key) === cleanPubkey);
      if (match) return match.name;
      return shortKey(pubkey);
    },
    [balance.public_key, peers.peers],
  );

  const openView = (next: View) => {
    setView(next);
    setMobileOpen(false);
  };

  // Guided tour: opens once automatically for a new browser, and from the Tour button.
  const [tourOpen, setTourOpen] = useState(false);
  useEffect(() => {
    if (isSpectator) return;
    try {
      if (!window.localStorage.getItem("consensus-tour-seen")) setTourOpen(true);
    } catch {
      // Storage unavailable: the Tour button still works.
    }
  }, [isSpectator]);
  const closeTour = () => {
    setTourOpen(false);
    try {
      window.localStorage.setItem("consensus-tour-seen", "1");
    } catch {
      // Ignore: the tour may simply reopen next time.
    }
  };

  // Find self node info
  const selfNodeName =
    (isSpectator ? "Room observer" : peers.peers.find((p) => p.public_key === balance.public_key)?.name) || "node";

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Open navigation"
          >
            {mobileOpen ? <X /> : <Menu />}
          </Button>

          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center rounded-md bg-primary text-primary-foreground">
              <Network className="h-4 w-4" />
            </div>
            <div className="hidden sm:block">
              <div className="text-sm font-semibold">Consensus Console</div>
              <div className="text-[11px] text-muted-foreground">Proof-of-Stake Network Monitor</div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            {isSpectator && (
              <span className="status status-info">
                <ShieldCheck className="h-3.5 w-3.5 mr-1" /> SPECTATOR / READ ONLY
              </span>
            )}
            <span className={`status ${wsConnected ? "status-online" : "status-neutral"}`}>
              <span className={`status-dot ${wsConnected ? "bg-success" : "bg-muted-foreground"}`} />
              {wsConnected ? "WS Live" : isSpectator ? "REST Sync · reconnecting" : "REST Sync"}
            </span>
            <span className="hidden text-xs text-muted-foreground md:inline">
              Updated{" "}
              {lastUpdate.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <div className="hidden h-7 w-px bg-border sm:block" />
            <Button
              variant="ghost"
              size="icon"
              title="Disconnect"
              aria-label="Disconnect"
              onClick={onDisconnect}
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px]">
        <aside
          className={`${
            mobileOpen ? "flex" : "hidden"
          } fixed inset-x-0 top-16 z-30 h-[calc(100vh-4rem)] flex-col border-r border-border bg-background p-4 lg:sticky lg:top-16 lg:flex lg:h-[calc(100vh-4rem)] lg:w-60 lg:shrink-0`}
        >
          <div className="mb-5 rounded-md border border-border bg-muted/50 p-3">
            <div className="flex items-center gap-2">
              <span className="status-dot bg-success" />
              <span className="text-sm font-medium">{selfNodeName}</span>
              <span className="ml-auto text-[10px] font-semibold uppercase text-primary">Connected</span>
            </div>
            <div className="mt-2 truncate font-mono text-[10px] text-muted-foreground">
              {isSpectator ? "Read-only room gateway" : connection.url}
            </div>
          </div>

          <nav className="space-y-1">
            {nav.map((item) => (
              <Button
                key={item.id}
                variant="ghost"
                className={`w-full justify-start ${
                  view === item.id ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                }`}
                onClick={() => openView(item.id)}
              >
                <item.icon />
                {item.label}
              </Button>
            ))}
          </nav>

          <div className="mt-auto border-t border-border pt-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Node Connection</span>
              <span className="font-medium text-success">Live API</span>
            </div>
            <div className="text-[11px] leading-4 text-muted-foreground">
              Connected directly to Docker container REST & Event WebSocket.
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-[1320px]">
            <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow">
                  <Radio className="h-3.5 w-3.5 text-primary" /> Live Network Feed
                </div>
                <h1 className="mt-3 text-2xl font-semibold sm:text-3xl">{viewTitles[view]}</h1>
                <p className="mt-1 text-sm text-muted-foreground">{viewDescriptions[view]}</p>
              </div>
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                {isSpectator && <Button variant="outline" onClick={async () => {
                    try { await downloadRunReport(connection); }
                    catch (err: any) { setToast(err.message || "PDF export failed."); }
                  }}>
                    <Download className="h-4 w-4" /> Export PDF report
                </Button>}
                {!isSpectator && (
                  <>
                    <Button variant="outline" onClick={() => setTourOpen(true)}>
                      <GraduationCap className="h-4 w-4" /> Tour
                    </Button>
                    {tourOpen && (
                      <Tutorial
                        connection={connection}
                        onNavigate={openView}
                        onRefresh={refreshAll}
                        onToast={setToast}
                        onClose={closeTour}
                      />
                    )}
                    <SpectatorShare connection={connection} onToast={setToast} />
                    {autoStake.available && (
                      <label className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
                        <Switch checked={autoStake.enabled} onCheckedChange={toggleAutoStake} />
                        Auto-stake
                      </label>
                    )}
                    <Button
                      variant="outline"
                      onClick={async () => {
                        try {
                          const res = await requestFaucet(connection, 50);
                          if (res.ok) {
                            setToast("Dev Faucet: 50 test coins added to your wallet!");
                            refreshAll();
                          }
                        } catch (err: any) {
                          setToast(err.message || "Failed to request test coins.");
                        }
                      }}
                      className="text-success border-success/30 hover:bg-success/10"
                    >
                      <Coins className="h-4 w-4" /> +50 Test Coins
                    </Button>
                    {view !== "mempool" && (
                      <Button variant="outline" onClick={() => openView("mempool")}>
                        <Send /> Send transaction
                      </Button>
                    )}
                    {view !== "validators" && (
                      <Button onClick={() => openView("validators")}>
                        <Coins /> Add stake
                      </Button>
                    )}
                  </>
                )}
              </div>
            </div>

            {view === "overview" && (
              <Overview
                balance={balance}
                chain={chain}
                peers={peers}
                countdown={countdown}
                mempool={mempool}
                stakers={stakers}
                slashed={slashed}
                invariants={invariants}
                getName={getName}
                onView={openView}
                onBlock={setSelectedBlock}
                onTx={setSelectedTx}
                isSpectator={isSpectator}
                metrics={metrics}
              />
            )}
            {view === "explorer" && (
              <Explorer
                chain={chain}
                slashed={slashed}
                getName={getName}
                onBlock={setSelectedBlock}
                onTx={setSelectedTx}
              />
            )}
            {view === "network" && (
              <NetworkPanel peers={peers} selfPk={balance.public_key} packets={packets} />
            )}
            {view === "validators" && (
              <Validators
                stakers={stakers}
                balance={balance}
                countdown={countdown}
                connection={connection}
                getName={getName}
                onRefresh={refreshAll}
                onToast={setToast}
                readOnly={isSpectator}
              />
            )}
            {view === "mempool" && (
              <Mempool
                mempool={mempool}
                connection={connection}
                getName={getName}
                onRefresh={refreshAll}
                onTx={setSelectedTx}
                onToast={setToast}
                readOnly={isSpectator}
              />
            )}
            {view === "attack_lab" && (isSpectator ? (
              <SpectatorAttackPanel connection={connection} event={attackEvent} slashed={slashed} />
            ) : (
              <AttackLab
                connection={connection}
                peers={peers}
                selfPublicKey={balance.public_key}
                slashed={slashed}
                getName={getName}
                onToast={setToast}
                onRefresh={refreshAll}
              />
            ))}
          </div>
        </main>
      </div>

      <BlockDialog block={selectedBlock} onClose={() => setSelectedBlock(null)} />
      <TransactionDialog transaction={selectedTx} onClose={() => setSelectedTx(null)} />

      {toast && (
        <div
          role="status"
          className="fixed bottom-5 right-5 z-50 rounded-md border border-border bg-foreground px-4 py-3 text-sm text-background shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  );
}

const viewTitles: Record<View, string> = {
  overview: "Overview",
  explorer: "Explorer",
  network: "Network",
  validators: "Validators",
  mempool: "Mempool",
  attack_lab: "Attack Lab",
};

const viewDescriptions: Record<View, string> = {
  overview: "Network activity and consensus health at a glance.",
  explorer: "Follow verified blocks and their transaction history.",
  network: "Inspect connected peers and network topology.",
  validators: "Review stake distribution and validator probability.",
  mempool: "Inspect and submit pending transactions.",
  attack_lab: "Simulate double-sign attacks and test security mechanisms.",
};

function InvariantRow({
  title,
  state,
  okDetail,
  failDetail,
}: {
  title: string;
  state: boolean | undefined;
  okDetail: string;
  failDetail: string;
}) {
  const status = state === undefined ? "checking" : state ? "ok" : "fail";
  return (
    <div
      className={`flex items-center gap-2 rounded p-2.5 ${
        status === "fail" ? "bg-destructive/10" : "bg-muted/40"
      }`}
    >
      <span
        className={`font-bold ${
          status === "fail"
            ? "text-destructive"
            : status === "ok"
              ? "text-success"
              : "text-muted-foreground"
        }`}
      >
        {status === "fail" ? "✗" : "✓"}
      </span>
      <div>
        <div className="font-medium">{title}</div>
        <div
          className={`text-[10px] ${
            status === "fail" ? "text-destructive" : "text-muted-foreground"
          }`}
        >
          {status === "checking" ? "Checking..." : status === "ok" ? okDetail : failDetail}
        </div>
      </div>
    </div>
  );
}

function PanelHeading({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>
      </div>
      {action}
    </div>
  );
}

function Overview({
  balance,
  chain,
  peers,
  countdown,
  mempool,
  stakers,
  slashed,
  invariants,
  getName,
  onView,
  onBlock,
  onTx,
  isSpectator,
  metrics,
}: {
  balance: BalanceResponse;
  chain: ChainResponse;
  peers: PeersResponse;
  countdown: number;
  mempool: MempoolResponse;
  stakers: StakersResponse;
  slashed: NodeSlashedEvent | null;
  invariants: InvariantsResponse | null;
  getName: (pk: string) => string;
  onView: (v: View) => void;
  onBlock: (b: Block) => void;
  onTx: (t: Transaction) => void;
  isSpectator: boolean;
  metrics: MetricsResponse | null;
}) {
  const totalStake = Object.values(stakers.stakers).reduce((a, b) => a + b, 0);

  const stats = [
    [
      WalletCards,
      "Balance",
      isSpectator ? "—" : `${balance.balance} coins`,
      isSpectator ? "No peer wallet is attached" : balance.pending_income
        ? `+${balance.pending_income} pending confirmation${
            balance.auto_faucet_pending ? ` (incl. ${balance.auto_faucet_pending} auto-faucet)` : ""
          }`
        : "Your wallet balance",
    ],
    [Clock3, "Epoch Ends In", `${countdown}s`, "Next block selection"],
    [Users, "Connected Peers", `${peers.peers.length}`, "Discovered via Signalling"],
    [Blocks, "Chain Height", String(chain.blocks.length), "Verified blocks"],
    [
      Database,
      "Pending Txs",
      String(mempool.transactions.length),
      `${mempool.transactions.reduce((sum, tx) => sum + tx.payload, 0)} coins queued`,
    ],
  ] as const;

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map(([Icon, label, value, detail]) => (
          <div className="panel p-4" key={label}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{label}</span>
              <Icon className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3 text-2xl font-semibold">{value}</div>
            <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
          </div>
        ))}
      </div>
      {metrics && <div className="text-xs text-muted-foreground">Room {metrics.room_id} · {metrics.total_transactions} confirmed transactions · average block time {metrics.avg_block_time_sec}s</div>}

      {/* Consensus Invariants Panel */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-success" />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Live Consensus Invariants
            </span>
          </div>
          <span className="status status-online text-[11px]">Auto Verified</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 text-xs">
          <InvariantRow
            title="Chain Consensus"
            state={invariants?.honest_consensus}
            okDetail="Honest nodes synchronized"
            failDetail="Hash chain broken - a block's prevHash does not match"
          />
          <InvariantRow
            title="Supply Conservation"
            state={invariants?.supply_conserved}
            okDetail="No illegal inflation / overspending"
            failDetail="Total wallet balances don't match coins minted"
          />
          <InvariantRow
            title="Proposer Validation"
            state={invariants?.valid_proposers}
            okDetail="ECDSA signatures verified"
            failDetail="A block's signature does not match its claimed creator"
          />
        </div>
      </div>

      {slashed && (
        <div className="alert-danger">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div className="min-w-0">
              <div className="font-semibold">Malicious Node Slashed</div>
              <p className="mt-1 text-sm opacity-85">
                Validator <span className="font-mono">{getName(slashed.creator)}</span> attempted double-signing at block index {slashed.block_pos}. Stake slashed to zero!
              </p>
            </div>
            {!isSpectator && <Button
              variant="outline"
              size="sm"
              className="ml-auto shrink-0 border-current bg-transparent hover:bg-destructive/10"
              onClick={() => onView("validators")}
            >
              Inspect <ChevronRight />
            </Button>}
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.55fr_1fr]">
        <section className="panel overflow-hidden">
          <PanelHeading
            title="Latest Blocks"
            detail="Verified additions to the canonical chain"
            action={
              <Button variant="ghost" size="sm" onClick={() => onView("explorer")}>
                View all <ArrowRight />
              </Button>
            }
          />
          <div className="divide-y divide-border">
            {chain.blocks.length === 0 ? (
              <div className="p-5 text-center text-xs text-muted-foreground">No blocks mined yet.</div>
            ) : (
              [...chain.blocks]
                .reverse()
                .slice(0, 4)
                .map((block, index) => (
                  <button
                    key={block.id}
                    className="data-row w-full text-left"
                    onClick={() => onBlock(block)}
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-md bg-muted font-mono text-xs">
                      #{chain.blocks.length - index}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{shortKey(block.id, 14, 6)}</span>
                      <span className="text-xs text-muted-foreground">
                        by {getName(block.creator)} · {formatTime(block.ts)}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="block text-sm font-medium">
                        {block.transactions.length} tx
                      </span>
                      <span className="text-xs text-muted-foreground">{block.staked_amt} staked</span>
                    </span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </button>
                ))
            )}
          </div>
        </section>

        <section className="panel overflow-hidden">
          <PanelHeading title="Stake Distribution" detail={`${totalStake} total coins registered`} />
          <div className="space-y-4 p-5">
            {Object.keys(stakers.stakers).length === 0 ? (
              <div className="text-center text-xs text-muted-foreground">No registered stakers for this epoch.</div>
            ) : (
              Object.entries(stakers.stakers)
                .sort((a, b) => b[1] - a[1])
                .map(([key, amt]) => {
                  const probability = totalStake > 0 ? Math.round((amt / totalStake) * 100) : 0;
                  const isSelf = key === balance.public_key;
                  return (
                    <div key={key}>
                      <div className="mb-1.5 flex justify-between text-xs">
                        <span className="font-medium">
                          {getName(key)}{" "}
                          {isSelf && <em className="not-italic text-primary">· You</em>}
                        </span>
                        <span>{probability}% ({amt} coins)</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${probability}%` }}
                        />
                      </div>
                    </div>
                  );
                })
            )}
          </div>
        </section>
      </div>

      <section className="panel overflow-hidden">
        <PanelHeading
          title="Mempool Activity"
          detail="Transactions awaiting inclusion in next block"
          action={
            <Button variant="ghost" size="sm" onClick={() => onView("mempool")}>
              Open mempool <ArrowRight />
            </Button>
          }
        />
        <TransactionTable
          transactions={mempool.transactions.slice(0, 5)}
          getName={getName}
          onTx={onTx}
        />
      </section>
    </div>
  );
}

function Explorer({
  chain: liveChain,
  slashed,
  getName,
  onBlock,
  onTx,
}: {
  chain: ChainResponse;
  slashed: NodeSlashedEvent | null;
  getName: (pk: string) => string;
  onBlock: (b: Block) => void;
  onTx: (t: Transaction) => void;
}) {
  // Time-travel scrubber: `viewHeight` is how many blocks of history are shown, or null
  // to follow the live chain. Blocks are append-only, so slicing the chain replays it
  // exactly as it looked at that height; new blocks keep arriving while you look back.
  const total = liveChain.blocks.length;
  const [viewHeight, setViewHeight] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const shown = Math.min(viewHeight ?? total, total);
  const chain: ChainResponse = { ...liveChain, blocks: liveChain.blocks.slice(0, shown) };
  const replaying = viewHeight !== null && shown < total;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setViewHeight((current) => {
        const next = (current ?? total) + 1;
        if (next >= total) {
          setPlaying(false);
          return null;
        }
        return next;
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [playing, total]);

  const confirmedTxs = chain.blocks.reduce((sum, block) => sum + block.transactions.length, 0);
  const shownTip = chain.blocks[chain.blocks.length - 1];

  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Canonical Chain"
          detail={
            replaying
              ? `Replaying: block ${shown} of ${total} · newest first`
              : `${total} blocks · newest first`
          }
        />
        {total > 1 && (
          <div className="border-b border-border px-6 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (playing) return setPlaying(false);
                  setViewHeight(1);
                  setPlaying(true);
                }}
              >
                {playing ? "Pause" : "Replay from start"}
              </Button>
              <input
                type="range"
                aria-label="Time travel through the chain"
                className="h-2 min-w-[160px] flex-1 cursor-pointer accent-primary"
                min={1}
                max={total}
                value={shown}
                onChange={(e) => {
                  setPlaying(false);
                  const next = Number(e.target.value);
                  setViewHeight(next >= total ? null : next);
                }}
              />
              <Button
                variant={replaying ? "default" : "outline"}
                size="sm"
                disabled={!replaying}
                onClick={() => {
                  setPlaying(false);
                  setViewHeight(null);
                }}
              >
                Back to live
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {replaying ? "Time travel: " : "Live: "}
              {`chain height ${shown} · ${confirmedTxs} confirmed transaction${confirmedTxs === 1 ? "" : "s"}`}
              {shownTip ? ` · tip ${shortKey(shownTip.id, 8, 4)} at ${formatTime(shownTip.ts)}` : ""}
              {replaying ? ` · ${total - shown} newer block${total - shown === 1 ? "" : "s"} hidden` : ""}
            </p>
          </div>
        )}
        <div className="chain-scroll">
          <div className="flex min-w-max items-stretch gap-0 p-6">
            {[...chain.blocks].reverse().map((block, index) => {
              // Chain state is authoritative; the live event only covers the moment
              // before the next refresh lands.
              const isSlashed =
                block.slash_creator === true ||
                block.is_valid === false ||
                (slashed?.creator === block.creator && slashed.block_pos === chain.blocks.length - 1 - index);
              return (
                <div className="flex items-center" key={block.id}>
                  <button
                    onClick={() => onBlock(block)}
                    className={`chain-card ${isSlashed ? "chain-card-danger" : ""}`}
                  >
                    <div className="flex items-start justify-between">
                      <span className="font-mono text-xs text-muted-foreground">
                        BLOCK #{chain.blocks.length - index}
                      </span>
                      {isSlashed ? (
                        <span className="status status-danger">
                          <AlertTriangle className="h-3 w-3" />
                          Slashed
                        </span>
                      ) : (
                        <span className="status status-online">
                          <span className="status-dot" />
                          Verified
                        </span>
                      )}
                    </div>
                    <div className="mt-8 text-base font-semibold">{getName(block.creator)}</div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      {shortKey(block.id, 11, 5)}
                    </div>
                    <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4">
                      <div>
                        <dt className="text-[10px] uppercase text-muted-foreground">
                          Transactions
                        </dt>
                        <dd className="mt-1 text-sm font-medium">{block.transactions.length}</dd>
                      </div>
                      <div>
                        <dt className="text-[10px] uppercase text-muted-foreground">Stake</dt>
                        <dd className="mt-1 text-sm font-medium">{block.staked_amt}</dd>
                      </div>
                    </dl>
                    <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                      <span>{formatTime(block.ts)}</span>
                      <ChevronRight className="h-4 w-4" />
                    </div>
                  </button>
                  {index < chain.blocks.length - 1 && (
                    <div className="chain-link">
                      <span />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <PanelHeading
          title="Confirmed Transactions"
          detail="Transactions included in verified blocks"
        />
        <TransactionTable
          transactions={chain.blocks.flatMap((b) => b.transactions)}
          getName={getName}
          onTx={onTx}
        />
      </section>
    </div>
  );
}

function TransactionTable({
  transactions,
  getName,
  onTx,
}: {
  transactions: Transaction[];
  getName: (pk: string) => string;
  onTx: (t: Transaction) => void;
}) {
  if (transactions.length === 0) {
    return (
      <div className="p-6 text-center text-xs text-muted-foreground">
        No transactions to display.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-[10px] uppercase text-muted-foreground">
            <th className="px-5 py-3 font-medium">Transaction ID</th>
            <th className="px-5 py-3 font-medium">From</th>
            <th className="px-5 py-3 font-medium">To</th>
            <th className="px-5 py-3 font-medium">Amount</th>
            <th className="px-5 py-3 font-medium">Time</th>
            <th className="w-10" />
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.id} className="border-b border-border last:border-0 hover:bg-muted/30">
              <td className="px-5 py-3 font-mono text-xs">{shortKey(tx.id, 12, 5)}</td>
              <td className="px-5 py-3 text-xs">{getName(tx.sender)}</td>
              <td className="px-5 py-3 text-xs">{getName(tx.receiver)}</td>
              <td className="px-5 py-3 text-sm font-medium">{tx.payload} coins</td>
              <td className="px-5 py-3 text-xs text-muted-foreground">{formatTime(tx.ts)}</td>
              <td>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onTx(tx)}
                  aria-label="View transaction"
                >
                  <ChevronRight />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Pt = { x: number; y: number };

type PacketKind = "tx" | "stake" | "block";
type Packet = { id: number; kind: PacketKind; fromKey: string };

const PACKET_STYLES: Record<PacketKind, string> = {
  tx: "h-2.5 w-2.5 rounded-full bg-primary shadow-[0_0_8px_2px] shadow-primary/60",
  stake: "h-2.5 w-2.5 rounded-full bg-warning shadow-[0_0_8px_2px] shadow-warning/60",
  block: "h-3.5 w-3.5 rounded-sm bg-success shadow-[0_0_10px_3px] shadow-success/60",
};

/** One glowing dot travelling between two node positions (fractions of the canvas). */
function PacketDot({ from, to, kind }: { from: Pt; to: Pt; kind: PacketKind }) {
  const [moving, setMoving] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => requestAnimationFrame(() => setMoving(true)));
    return () => cancelAnimationFrame(frame);
  }, []);
  const at = moving ? to : from;
  return (
    <div
      className={`pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2 ${PACKET_STYLES[kind]}`}
      style={{
        left: `${at.x * 100}%`,
        top: `${at.y * 100}%`,
        opacity: moving ? 0 : 1,
        transition: "left 1.1s ease-in-out, top 1.1s ease-in-out, opacity 0.35s ease-in 0.85s",
      }}
    />
  );
}

function NetworkPanel({
  peers,
  selfPk,
  packets,
}: {
  peers: PeersResponse;
  selfPk: string;
  packets: Packet[];
}) {
  const peerList = peers.peers;
  const canvasRef = useRef<HTMLDivElement>(null);
  // Positions are fractions (0..1) of the canvas so lines and cards always
  // share one coordinate space. Dragged cards override the default layout.
  const [moved, setMoved] = useState<Record<string, Pt>>({});
  const [dragging, setDragging] = useState<string | null>(null);

  const keyOf = (peer: PeersResponse["peers"][number]) => `${peer.name}@${peer.host}:${peer.port}`;

  // The signalling server's whole purpose is peers connecting directly to
  // each other, forming a mesh - so the honest topology for any known peer
  // list is a complete graph (every peer <-> every other peer), not
  // something we need a separate connection-pair endpoint to discover.
  const positions: Pt[] = peerList.map((peer, i) => {
    const custom = moved[keyOf(peer)];
    if (custom) return custom;
    if (peerList.length === 1) return { x: 0.5, y: 0.5 };
    const angle = (2 * Math.PI * i) / peerList.length - Math.PI / 2;
    return { x: 0.5 + 0.34 * Math.cos(angle), y: 0.5 + 0.34 * Math.sin(angle) };
  });
  const edges: Array<{ key: string; from: Pt; to: Pt }> = [];
  for (let i = 0; i < positions.length; i++) {
    for (let j = i + 1; j < positions.length; j++) {
      const from = positions[i];
      const to = positions[j];
      if (from && to) edges.push({ key: `${i}-${j}`, from, to });
    }
  }

  const dragTo = (key: string, clientX: number, clientY: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return;
    const clamp = (v: number) => Math.min(0.95, Math.max(0.05, v));
    setMoved((prev) => ({
      ...prev,
      [key]: { x: clamp((clientX - rect.left) / rect.width), y: clamp((clientY - rect.top) / rect.height) },
    }));
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Peer Mesh Topology"
          detail={`Full mesh - every peer connects directly to every other peer (${edges.length} link${edges.length === 1 ? "" : "s"}). Drag nodes to rearrange.`}
        />
        <div ref={canvasRef} className="relative h-[440px] touch-none select-none overflow-hidden bg-grid">
          <svg className="absolute inset-0 h-full w-full">
            {edges.map(({ key, from, to }) => (
              <line
                key={key}
                x1={`${from.x * 100}%`}
                y1={`${from.y * 100}%`}
                x2={`${to.x * 100}%`}
                y2={`${to.y * 100}%`}
                className="stroke-border"
                strokeWidth={1.5}
              />
            ))}
          </svg>
          {peerList.map((peer, i) => {
            const isSelf = peer.public_key === selfPk;
            const pos = positions[i];
            if (!pos) return null;
            const key = keyOf(peer);
            return (
              <div
                key={key}
                onPointerDown={(e) => {
                  e.currentTarget.setPointerCapture(e.pointerId);
                  setDragging(key);
                }}
                onPointerMove={(e) => {
                  if (dragging === key) dragTo(key, e.clientX, e.clientY);
                }}
                onPointerUp={() => setDragging(null)}
                onPointerCancel={() => setDragging(null)}
                className={`absolute flex w-28 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-lg border p-3 text-center shadow-sm ${
                  dragging === key ? "z-10 cursor-grabbing shadow-lg" : "cursor-grab"
                } ${
                  isSelf
                    ? "border-primary bg-primary/10 font-semibold"
                    : "border-border bg-card hover:border-primary/50"
                }`}
                style={{ left: `${pos.x * 100}%`, top: `${pos.y * 100}%` }}
              >
                <Server className={`h-6 w-6 ${isSelf ? "text-primary" : "text-muted-foreground"}`} />
                <div className="mt-1.5 text-xs font-medium">{peer.name}</div>
                <div className="font-mono text-[10px] text-muted-foreground">
                  {peer.host}:{peer.port}
                </div>
                {isSelf && <span className="mt-1 text-[9px] uppercase text-primary font-bold">You</span>}
              </div>
            );
          })}
          {packets.flatMap((packet) => {
            const originIndex = peerList.findIndex(
              (peer) => peer.public_key && normKey(peer.public_key) === normKey(packet.fromKey),
            );
            const origin = positions[originIndex];
            if (!origin) return [];
            return peerList.flatMap((_, j) => {
              const target = positions[j];
              return j === originIndex || !target
                ? []
                : [<PacketDot key={`${packet.id}-${j}`} from={origin} to={target} kind={packet.kind} />];
            });
          })}
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-border px-6 py-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-primary" /> Transaction</span>
          <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-warning" /> Stake</span>
          <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-success" /> New block</span>
          <span>Packets fly from the sender to every other node as they happen.</span>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <PanelHeading title="Known Peers" detail={`${peerList.length} nodes active in room`} />
        <div className="divide-y divide-border">
          {peerList.map((peer) => {
            const isSelf = peer.public_key === selfPk;
            return (
              <div className="p-4" key={peer.name + peer.public_key}>
                <div className="flex items-center gap-3">
                  <span className="status-dot bg-success" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      {peer.name}
                      {isSelf && <span className="text-xs text-primary font-semibold">You</span>}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                      {peer.host}:{peer.port}
                    </div>
                  </div>
                  <span className="status status-online">Connected</span>
                </div>
                <div className="mt-2 pl-5">
                  <CopyValue value={peer.public_key} compact />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function Validators({
  stakers,
  balance,
  countdown,
  connection,
  getName,
  onRefresh,
  onToast,
  readOnly,
}: {
  stakers: StakersResponse;
  balance: BalanceResponse;
  countdown: number;
  connection: Connection;
  getName: (pk: string) => string;
  onRefresh: () => void;
  onToast: (s: string) => void;
  readOnly: boolean;
}) {
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const stakerEntries = Object.entries(stakers.stakers);
  const total = stakerEntries.reduce((a, b) => a + b[1], 0);

  const handleSubmitStake = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than zero.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await submitStake(connection, value);
      if (!res.ok) {
        setError(res.error || "Failed to register stake.");
      } else {
        setAmount("");
        onToast(`Stake registered! Block selection in ${res.creating_block_in_seconds}s.`);
        onRefresh();
      }
    } catch (err: any) {
      setError(err.message || "Error submitting stake.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Validator Leaderboard"
          detail={`${total} coins staked · next epoch selection in ${countdown}s`}
        />
        <div className="divide-y divide-border">
          {stakerEntries.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted-foreground">
              No registered stakers for this epoch.
            </div>
          ) : (
            stakerEntries
              .sort((a, b) => b[1] - a[1])
              .map(([key, amt], i) => {
                const chance = total ? Math.round((amt / total) * 100) : 0;
                const isSelf = key === balance.public_key;

                return (
                  <div key={key} className="p-5">
                    <div className="flex items-center gap-4">
                      <span className="grid h-8 w-8 place-items-center rounded-md bg-muted text-xs font-semibold">
                        #{i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                          {getName(key)}
                          {isSelf && <span className="status status-info">You</span>}
                        </div>
                        <div className="mt-1">
                          <CopyValue value={key} compact />
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-base font-semibold">{amt} coins</div>
                        <div className="text-xs text-muted-foreground">{chance}% probability</div>
                      </div>
                    </div>
                    <div className="ml-12 mt-3 h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${chance}%` }}
                      />
                    </div>
                  </div>
                );
              })
          )}
        </div>
      </section>

      {!readOnly && <section className="panel self-start p-5">
        <div className="mb-5">
          <h2 className="text-sm font-semibold">Register Stake</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Commit coins to participate in PoS block selection.
          </p>
        </div>

        <form onSubmit={handleSubmitStake}>
          <Label htmlFor="stake">Amount</Label>
          <div className="relative mt-2">
            <Input
              id="stake"
              type="number"
              min="1"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0"
              className="pr-16"
            />
            <span className="absolute right-3 top-2 text-xs text-muted-foreground">coins</span>
          </div>

          <div className="mt-2 flex justify-between text-xs text-muted-foreground">
            <span>Available balance</span>
            <span>{balance.balance} coins</span>
          </div>

          {Number(amount) > 0 && (
            <div className="mt-2 flex justify-between text-xs text-muted-foreground">
              <span>Your chance of being picked</span>
              <span className="font-medium text-primary">
                {Math.round((Number(amount) / (total + Number(amount))) * 100)}%
              </span>
            </div>
          )}

          {error && (
            <p role="alert" className="mt-3 text-xs text-destructive">
              {error}
            </p>
          )}

          <Button className="mt-5 w-full" disabled={loading}>
            <Coins /> {loading ? "Registering..." : "Register Stake"}
          </Button>
        </form>
      </section>}
      <div className="xl:col-span-2">
        <ElectionExplainer stakers={stakers} getName={getName} selfPk={balance.public_key} />
      </div>
    </div>
  );
}

function Mempool({
  mempool,
  connection,
  getName,
  onRefresh,
  onTx,
  onToast,
  readOnly,
}: {
  mempool: MempoolResponse;
  connection: Connection;
  getName: (pk: string) => string;
  onRefresh: () => void;
  onTx: (t: Transaction) => void;
  onToast: (s: string) => void;
  readOnly: boolean;
}) {
  const [receiver, setReceiver] = useState("");
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmitTx = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(amount);

    if (!receiver.trim() || !Number.isFinite(value) || value <= 0) {
      setError("Enter a valid receiver and amount greater than zero.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await submitTransaction(connection, receiver.trim(), value);
      if (!res.ok) {
        setError("Failed to submit transaction.");
      } else {
        setReceiver("");
        setAmount("");
        onToast(`Transaction ${shortKey(res.transaction_id || "", 8, 5)} broadcasted!`);
        onRefresh();
      }
    } catch (err: any) {
      setError(err.message || "Error submitting transaction.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Pending Transactions"
          detail={`${mempool.transactions.length} transactions in mempool`}
        />
        <TransactionTable transactions={mempool.transactions} getName={getName} onTx={onTx} />
      </section>

      {!readOnly && <section className="panel self-start p-5">
        <h2 className="text-sm font-semibold">Send Transaction</h2>
        <p className="mt-1 text-xs text-muted-foreground">Broadcast transaction to the P2P network.</p>

        <form className="mt-5 space-y-4" onSubmit={handleSubmitTx}>
          <div>
            <Label htmlFor="receiver">Receiver</Label>
            <Input
              id="receiver"
              className="mt-2 font-mono text-xs"
              value={receiver}
              onChange={(e) => setReceiver(e.target.value)}
              placeholder="Peer name (e.g. bob) or PEM key"
            />
          </div>

          <div>
            <Label htmlFor="tx-amount">Amount</Label>
            <div className="relative mt-2">
              <Input
                id="tx-amount"
                type="number"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
                className="pr-16"
              />
              <span className="absolute right-3 top-2 text-xs text-muted-foreground">coins</span>
            </div>
          </div>

          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          )}

          <Button className="w-full" disabled={loading}>
            <Send /> {loading ? "Broadcasting..." : "Submit Transaction"}
          </Button>
        </form>
      </section>}
    </div>
  );
}

function SpectatorAttackPanel({
  connection,
  event,
  slashed,
}: {
  connection: Connection;
  event: any;
  slashed: NodeSlashedEvent | null;
}) {
  const [state, setState] = useState<AttackLabState>({ blocked_peers: [], latency_ms: 0, censored_receivers: [] });
  useEffect(() => {
    let active = true;
    const refresh = () => fetchAttackLabState(connection).then((value) => { if (active) setState(value); }).catch(() => {});
    refresh();
    const timer = window.setInterval(refresh, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [connection]);
  return (
    <div className="space-y-4">
      <div className="panel p-5">
        <h2 className="text-sm font-semibold">Observed Attack Lab State</h2>
        <p className="mt-2 text-xs text-muted-foreground">Read-only live state from the selected room peer.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3 text-sm">
          <div>Partitioned peers: {state.blocked_peers.length}</div>
          <div>Outbound latency: {state.latency_ms} ms</div>
          <div>Censorship rules: {state.censored_receivers.length}</div>
        </div>
      </div>
      {event && <div className="panel p-5"><h3 className="text-sm font-semibold">Latest live attack event</h3><p className="mt-2 text-xs">{event.attack || event.type}: {JSON.stringify(event)}</p></div>}
      {slashed && <div className="alert-danger">Slashing observed for block {slashed.block_pos} (creator {shortKey(slashed.creator)}).</div>}
      <div className="panel p-5 text-xs text-muted-foreground">Attack activity contains only events observed while this gateway was connected. The run report labels state snapshots separately from event history.</div>
    </div>
  );
}

function AttackLab({
  connection,
  peers,
  selfPublicKey,
  slashed,
  getName,
  onToast,
  onRefresh,
}: {
  connection: Connection;
  peers: PeersResponse;
  selfPublicKey: string;
  slashed: NodeSlashedEvent | null;
  getName: (pk: string) => string;
  onToast: (s: string) => void;
  onRefresh: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [managedPeers, setManagedPeers] = useState<ManagedPeerSummary[]>([]);
  const [selectedManagedPeer, setSelectedManagedPeer] = useState("");
  const [selectedPeerKeys, setSelectedPeerKeys] = useState<string[]>([]);
  const [latencyInput, setLatencyInput] = useState("1500");
  const [censorReceiver, setCensorReceiver] = useState("");
  const [attackState, setAttackState] = useState<AttackLabState>({ blocked_peers: [], latency_ms: 0, censored_receivers: [] });

  useEffect(() => {
    fetchAttackLabState(connection).then(setAttackState).catch(() => {});
    listManagedPeers().then((items) => {
      setManagedPeers(items);
      if (items[0]) setSelectedManagedPeer(items[0].peer_id);
    }).catch(() => setManagedPeers([]));
  }, [connection]);

  const applyAction = async (action: () => Promise<unknown>, success: string) => {
    setLoading(true);
    try {
      await action();
      onToast(success);
      setAttackState(await fetchAttackLabState(connection));
      onRefresh();
    } catch (err: any) {
      onToast(err.message || "Attack control failed.");
    } finally {
      setLoading(false);
    }
  };

  const selectedCensorKey = peers.peers.find((peer) => peer.name === censorReceiver)?.public_key || "";
  const censorshipEnabled = Boolean(selectedCensorKey && attackState.censored_receivers.includes(selectedCensorKey));

  return (
    <div className="space-y-6">
      <div className="panel p-6 border-destructive/30 bg-destructive/5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-destructive font-semibold text-lg">
              <AlertTriangle className="h-5 w-5" />
              <span>Chaos Lab</span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground max-w-2xl leading-relaxed">
              Fault injection for demonstrating resilience: the controls below act on the node you are
              connected to (or, for Kill, on a managed node). To see slashing, join a node with
              &ldquo;Join as a malicious node&rdquo; ticked: it double-signs when elected, and honest nodes
              detect the conflicting blocks and slash it.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <div className="panel p-5 space-y-3">
          <h2 className="text-sm font-semibold">Kill a Managed Node</h2>
          <p className="text-xs text-muted-foreground">Stops a peer-manager subprocess. Fixed Compose peers cannot be stopped here.</p>
          <select className="w-full rounded-md border border-border bg-background p-2 text-sm" value={selectedManagedPeer} onChange={(e) => setSelectedManagedPeer(e.target.value)}>
            {managedPeers.length === 0 && <option value="">No managed peers running</option>}
            {managedPeers.map((item) => <option key={item.peer_id} value={item.peer_id}>{item.name} · {item.room_id}</option>)}
          </select>
          <Button variant="destructive" disabled={loading || !selectedManagedPeer} onClick={async () => {
            const stoppedId = selectedManagedPeer;
            const stoppedName = managedPeers.find((item) => item.peer_id === stoppedId)?.name || "Managed node";
            setLoading(true);
            try {
              await stopRoomPeer(stoppedId, connection.token);
              setManagedPeers((items) => items.filter((item) => item.peer_id !== stoppedId));
              setSelectedManagedPeer("");
              onToast(`${stoppedName} stopped; signalling and peer connections will update.`);
              onRefresh();
            } catch (err: any) {
              onToast(err.message || "Failed to stop managed node.");
            } finally {
              setLoading(false);
            }
          }}>Stop selected managed node</Button>
          <div className="text-xs text-muted-foreground">Managed nodes available: {managedPeers.length}</div>
        </div>

        <div className="panel p-5 space-y-3">
          <h2 className="text-sm font-semibold">Partition the P2P Network</h2>
          <p className="text-xs text-muted-foreground">Isolate selected peer identities from this node’s actual P2P links.</p>
          <div className="max-h-28 space-y-1 overflow-auto">
            {peers.peers.filter((peer) => peer.public_key !== selfPublicKey).map((peer) => (
              <label key={peer.public_key} className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={selectedPeerKeys.includes(peer.public_key)} onChange={(e) => setSelectedPeerKeys((keys) => e.target.checked ? [...keys, peer.public_key] : keys.filter((key) => key !== peer.public_key))} />
                {peer.name}
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <Button disabled={loading || selectedPeerKeys.length === 0} onClick={() => applyAction(() => setPeerPartition(connection, selectedPeerKeys), "Partition applied to selected P2P peers.")}>Partition links</Button>
            <Button variant="outline" disabled={loading || attackState.blocked_peers.length === 0} onClick={() => applyAction(() => healPeerPartition(connection), "Partition healed; peer reconnection started.")}>Heal network</Button>
          </div>
          <div className="text-xs text-muted-foreground">Currently isolated identities: {attackState.blocked_peers.length}</div>
        </div>

        <div className="panel p-5 space-y-3">
          <h2 className="text-sm font-semibold">Add P2P Latency</h2>
          <p className="text-xs text-muted-foreground">Delays every outbound P2P broadcast from this node.</p>
          <div className="flex items-center gap-2"><Input type="number" min="0" max="10000" value={latencyInput} onChange={(e) => setLatencyInput(e.target.value)} /><span className="text-xs text-muted-foreground">ms</span></div>
          <div className="flex gap-2">
            <Button disabled={loading} onClick={() => applyAction(() => setPeerLatency(connection, Number(latencyInput)), `P2P broadcast delay set to ${latencyInput} ms.`)}>Apply delay</Button>
            <Button variant="outline" disabled={loading} onClick={() => { setLatencyInput("0"); void applyAction(() => setPeerLatency(connection, 0), "P2P latency cleared."); }}>Clear</Button>
          </div>
          <div className="text-xs text-muted-foreground">Active outbound delay: {attackState.latency_ms} ms</div>
        </div>

        <div className="panel p-5 space-y-3">
          <h2 className="text-sm font-semibold">Censor Transactions</h2>
          <p className="text-xs text-muted-foreground">This node rejects matching transactions from its mempool and P2P intake.</p>
          <select className="w-full rounded-md border border-border bg-background p-2 text-sm" value={censorReceiver} onChange={(e) => setCensorReceiver(e.target.value)}>
            <option value="">Select a transaction recipient</option>
            {peers.peers.filter((peer) => peer.public_key !== selfPublicKey).map((peer) => <option key={peer.public_key} value={peer.name}>{peer.name}</option>)}
          </select>
          <Button disabled={loading || !censorReceiver} onClick={() => applyAction(() => setPeerCensorship(connection, censorReceiver, !censorshipEnabled), censorshipEnabled ? `Censorship for ${censorReceiver} disabled.` : `Transactions to ${censorReceiver} are now censored by this node.`)}>
            {censorshipEnabled ? "Stop censorship" : "Start censorship"}
          </Button>
          <div className="text-xs text-muted-foreground">Active recipient rules: {attackState.censored_receivers.length}</div>
          {attackState.censored_receivers.length > 0 && <div className="text-xs text-destructive">Censoring: {attackState.censored_receivers.map(getName).join(", ")}</div>}
        </div>

        <div className="panel p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <ShieldCheck className="h-4 w-4 text-success" />
            <span>Target Malicious Node</span>
          </div>
          {managedPeers.filter((item) => item.role === "malicious").length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
              No malicious node is running. Join one from the join screen with "Join as a malicious node"
              ticked; it will double-sign conflicting blocks whenever it is elected.
            </div>
          ) : (
            managedPeers
              .filter((item) => item.role === "malicious")
              .map((item) => (
                <div key={item.peer_id} className="rounded-lg border border-border p-3 text-xs space-y-2 bg-muted/30">
                  <div className="flex justify-between font-medium">
                    <span>Node Name</span>
                    <span className="font-mono text-destructive font-bold">{item.name}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Room</span>
                    <span className="font-mono">{item.room_id}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Behavior</span>
                    <span>Double-Sign Conflicting Blocks</span>
                  </div>
                </div>
              ))
          )}
        </div>

        <div className="panel p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <ShieldCheck className="h-4 w-4 text-success" />
            <span>Consensus Slashing Invariant</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            When a validator signs two conflicting blocks at the same height slot, honest nodes detect the invalid signature, broadcast <code className="rounded bg-muted px-1 py-0.5">slash_announcement</code>, and reduce the offender's stake to zero.
          </p>
        </div>
      </div>

      {slashed && (
        <div className="alert-danger">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0 text-destructive mt-0.5" />
            <div>
              <div className="font-semibold text-base">Malicious Node Slashed</div>
              <p className="mt-1 text-sm opacity-90 leading-relaxed">
                Validator <span className="font-mono font-bold">{getName(slashed.creator)}</span> produced conflicting double-sign signatures at block index {slashed.block_pos}. Stake immediately slashed to zero across all honest nodes!
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
