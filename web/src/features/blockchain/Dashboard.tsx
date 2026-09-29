import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Blocks,
  ChevronRight,
  Clock3,
  Coins,
  Database,
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BlockDialog, TransactionDialog } from "./DetailDialog";
import {
  initialMockData,
  mockPresentation,
  type Block,
  type MempoolResponse,
  type StakersResponse,
  type Transaction,
} from "./mock-data";
import { submitMockStake, submitMockTransaction } from "./mock-service";
import { CopyValue, formatTime, shortKey } from "./utils";
import type { Connection } from "./ConnectionScreen";

type View = "overview" | "explorer" | "network" | "validators" | "mempool";
const nav: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "explorer", label: "Explorer", icon: Blocks },
  { id: "network", label: "Network", icon: Network },
  { id: "validators", label: "Validators", icon: ShieldCheck },
  { id: "mempool", label: "Mempool", icon: Database },
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
  const [mempool, setMempool] = useState<MempoolResponse>(() =>
    structuredClone(initialMockData.mempool),
  );
  const [stakers, setStakers] = useState<StakersResponse>(() =>
    structuredClone(initialMockData.stakers),
  );
  const [countdown, setCountdown] = useState(initialMockData.stakers.epoch_ends_in_seconds);
  const [selectedBlock, setSelectedBlock] = useState<Block | null>(null);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [toast, setToast] = useState("");
  const [lastUpdate, setLastUpdate] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => {
      setCountdown((v) => (v <= 1 ? initialMockData.stakers.epoch_ends_in_seconds : v - 1));
      setLastUpdate(new Date());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const openView = (next: View) => {
    setView(next);
    setMobileOpen(false);
  };
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
              <div className="text-[11px] text-muted-foreground">Proof-of-stake monitor</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="status status-online">
              <span className="status-dot" />
              Online
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
          className={`${mobileOpen ? "flex" : "hidden"} fixed inset-x-0 top-16 z-30 h-[calc(100vh-4rem)] flex-col border-r border-border bg-background p-4 lg:sticky lg:top-16 lg:flex lg:h-[calc(100vh-4rem)] lg:w-60 lg:shrink-0`}
        >
          <div className="mb-5 rounded-md border border-border bg-muted/50 p-3">
            <div className="flex items-center gap-2">
              <span className="status-dot bg-success" />
              <span className="text-sm font-medium">alpha-node</span>
              <span className="ml-auto text-[10px] font-semibold uppercase text-primary">You</span>
            </div>
            <div className="mt-2 truncate font-mono text-[10px] text-muted-foreground">
              {connection.url}
            </div>
          </div>
          <nav className="space-y-1">
            {nav.map((item) => (
              <Button
                key={item.id}
                variant="ghost"
                className={`w-full justify-start ${view === item.id ? "bg-accent text-accent-foreground" : "text-muted-foreground"}`}
                onClick={() => openView(item.id)}
              >
                <item.icon />
                {item.label}
              </Button>
            ))}
          </nav>
          <div className="mt-auto border-t border-border pt-4">
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Simulation mode</span>
              <span className="font-medium text-primary">Active</span>
            </div>
            <div className="text-[11px] leading-4 text-muted-foreground">
              Data follows the node REST contract. No backend requests are made.
            </div>
          </div>
        </aside>
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-[1320px]">
            <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="eyebrow">
                  <Radio className="h-3.5 w-3.5" /> Live simulation
                </div>
                <h1 className="mt-3 text-2xl font-semibold capitalize sm:text-3xl">{view}</h1>
                <p className="mt-1 text-sm text-muted-foreground">{viewDescriptions[view]}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => openView("mempool")}>
                  <Send /> Send transaction
                </Button>
                <Button onClick={() => openView("validators")}>
                  <Coins /> Add stake
                </Button>
              </div>
            </div>
            {view === "overview" && (
              <Overview
                countdown={countdown}
                mempool={mempool}
                onView={openView}
                onBlock={setSelectedBlock}
                onTx={setSelectedTx}
                stakers={stakers}
              />
            )}
            {view === "explorer" && <Explorer onBlock={setSelectedBlock} onTx={setSelectedTx} />}
            {view === "network" && <NetworkPanel />}
            {view === "validators" && (
              <Validators
                stakers={stakers}
                setStakers={setStakers}
                countdown={countdown}
                onToast={setToast}
              />
            )}
            {view === "mempool" && (
              <Mempool
                mempool={mempool}
                setMempool={setMempool}
                onTx={setSelectedTx}
                onToast={setToast}
              />
            )}
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

const viewDescriptions: Record<View, string> = {
  overview: "Network activity and consensus health at a glance.",
  explorer: "Follow verified blocks and their transaction history.",
  network: "Inspect connected peers and network topology.",
  validators: "Review stake distribution and validator probability.",
  mempool: "Inspect and submit pending transactions.",
};
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
  countdown,
  mempool,
  stakers,
  onView,
  onBlock,
  onTx,
}: {
  countdown: number;
  mempool: MempoolResponse;
  stakers: StakersResponse;
  onView: (v: View) => void;
  onBlock: (b: Block) => void;
  onTx: (t: Transaction) => void;
}) {
  const totalStake = Object.values(stakers.stakers).reduce((a, b) => a + b, 0);
  const stats = [
    [WalletCards, "Balance", `${initialMockData.balance.balance} coins`, "+12 this epoch"],
    [Clock3, "Epoch ends", `00:${String(countdown).padStart(2, "0")}`, "Block selection pending"],
    [
      Users,
      "Connected peers",
      `${initialMockData.peers.peers.length - 1} / ${initialMockData.peers.peers.length}`,
      "1 peer unreachable",
    ],
    [Blocks, "Chain height", String(initialMockData.chain.blocks.length), "Last block 42s ago"],
    [
      Database,
      "Pending txs",
      String(mempool.transactions.length),
      `${mempool.transactions.reduce((sum, transaction) => sum + transaction.payload, 0)} coins queued`,
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
      <div className="alert-danger">
        <div className="flex gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <div className="font-semibold">Double-sign detected — validator slashed</div>
            <p className="mt-1 text-sm opacity-85">
              <span className="font-mono">mallory</span> produced conflicting blocks at position{" "}
              {initialMockData.slashed.block_pos}. Stake reduced to zero.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto shrink-0 border-current bg-transparent hover:bg-destructive/10"
            onClick={() => onView("validators")}
          >
            Inspect <ChevronRight />
          </Button>
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.55fr_1fr]">
        <section className="panel overflow-hidden">
          <PanelHeading
            title="Latest blocks"
            detail="Verified additions to the canonical chain"
            action={
              <Button variant="ghost" size="sm" onClick={() => onView("explorer")}>
                View all <ArrowRight />
              </Button>
            }
          />
          <div className="divide-y divide-border">
            {[...initialMockData.chain.blocks]
              .reverse()
              .slice(0, 3)
              .map((block, index) => (
                <button
                  key={block.id}
                  className="data-row w-full text-left"
                  onClick={() => onBlock(block)}
                >
                  <span className="grid h-8 w-8 place-items-center rounded-md bg-muted font-mono text-xs">
                    #{initialMockData.chain.blocks.length - index}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{block.id}</span>
                    <span className="text-xs text-muted-foreground">
                      by {mockPresentation.namesByKey[block.creator]} · {formatTime(block.ts)}
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
              ))}
          </div>
        </section>
        <section className="panel overflow-hidden">
          <PanelHeading title="Stake distribution" detail={`${totalStake} coins registered`} />
          <div className="space-y-4 p-5">
            {Object.entries(stakers.stakers)
              .filter(([, amt]) => amt > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([key, amt]) => {
                const probability = Math.round((amt / totalStake) * 100);
                return (
                  <div key={key}>
                    <div className="mb-1.5 flex justify-between text-xs">
                      <span className="font-medium">
                        {mockPresentation.namesByKey[key]}{" "}
                        {key === initialMockData.balance.public_key && (
                          <em className="not-italic text-primary">· You</em>
                        )}
                      </span>
                      <span>{probability}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${probability}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </section>
      </div>
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Mempool activity"
          detail="Transactions awaiting confirmation"
          action={
            <Button variant="ghost" size="sm" onClick={() => onView("mempool")}>
              Open mempool <ArrowRight />
            </Button>
          }
        />
        <TransactionTable transactions={mempool.transactions.slice(0, 3)} onTx={onTx} />
      </section>
    </div>
  );
}

function Explorer({
  onBlock,
  onTx,
}: {
  onBlock: (b: Block) => void;
  onTx: (t: Transaction) => void;
}) {
  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Canonical chain"
          detail={`${initialMockData.chain.blocks.length} blocks · newest first`}
        />
        <div className="chain-scroll">
          <div className="flex min-w-max items-stretch gap-0 p-6">
            {[...initialMockData.chain.blocks].reverse().map((block, index) => {
              const danger = block.creator === initialMockData.slashed.creator;
              return (
                <div className="flex items-center" key={block.id}>
                  <button
                    onClick={() => onBlock(block)}
                    className={`chain-card ${danger ? "chain-card-danger" : ""}`}
                  >
                    <div className="flex items-start justify-between">
                      <span className="font-mono text-xs text-muted-foreground">
                        BLOCK {initialMockData.chain.blocks.length - index}
                      </span>
                      {danger ? (
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
                    <div className="mt-8 text-base font-semibold">
                      {mockPresentation.namesByKey[block.creator]}
                    </div>
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
                  {index < initialMockData.chain.blocks.length - 1 && (
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
          title="Confirmed transactions"
          detail="Transactions included in verified blocks"
        />
        <TransactionTable
          transactions={initialMockData.chain.blocks.flatMap((b) => b.transactions)}
          onTx={onTx}
        />
      </section>
    </div>
  );
}

function TransactionTable({
  transactions,
  onTx,
}: {
  transactions: Transaction[];
  onTx: (t: Transaction) => void;
}) {
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
              <td className="px-5 py-3 text-xs">
                {mockPresentation.namesByKey[tx.sender] ?? shortKey(tx.sender)}
              </td>
              <td className="px-5 py-3 text-xs">
                {mockPresentation.namesByKey[tx.receiver] ?? shortKey(tx.receiver)}
              </td>
              <td className="px-5 py-3 text-sm font-medium">{tx.payload}</td>
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

function NetworkPanel() {
  const peers = initialMockData.peers.peers;
  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
      <section className="panel overflow-hidden">
        <PanelHeading title="Peer topology" detail="Current network mesh" />
        <div className="relative h-[420px] overflow-hidden bg-grid">
          <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
            {[
              [50, 50, 24, 25],
              [50, 50, 76, 25],
              [50, 50, 24, 76],
              [50, 50, 76, 76],
            ].map((a, i) => (
              <line
                key={i}
                x1={`${a[0]}%`}
                y1={`${a[1]}%`}
                x2={`${a[2]}%`}
                y2={`${a[3]}%`}
                className={i === 3 ? "stroke-destructive" : "stroke-border"}
                strokeWidth="2"
                strokeDasharray={i === 2 ? "6 6" : "0"}
              />
            ))}
          </svg>
          {peers.map((peer, i) => {
            const pos = i === 0 ? [50, 50] : i === 1 ? [24, 25] : i === 2 ? [24, 76] : [76, 76];
            const state =
              mockPresentation.peerStatuses[
                peer.name as keyof typeof mockPresentation.peerStatuses
              ];
            return (
              <div
                key={peer.name}
                className={`topology-node topology-${state}`}
                style={{ left: `${pos[0]}%`, top: `${pos[1]}%` }}
              >
                <Server className="h-5 w-5" />
                <span>{peer.name}</span>
                {i === 0 && <small>You</small>}
              </div>
            );
          })}
        </div>
      </section>
      <section className="panel overflow-hidden">
        <PanelHeading title="Known peers" detail={`${peers.length} nodes discovered`} />
        <div className="divide-y divide-border">
          {peers.map((peer) => {
            const state =
              mockPresentation.peerStatuses[
                peer.name as keyof typeof mockPresentation.peerStatuses
              ];
            return (
              <div
                className={`p-4 ${state === "malicious" ? "bg-destructive/5" : ""}`}
                key={peer.name}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`status-dot ${state === "offline" ? "bg-muted-foreground" : state === "malicious" ? "bg-destructive" : "bg-success"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      {peer.name}
                      {peer.public_key === initialMockData.balance.public_key && (
                        <span className="text-xs text-primary">You</span>
                      )}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                      {peer.host}:{peer.port}
                    </div>
                  </div>
                  <span
                    className={`status ${state === "malicious" ? "status-danger" : state === "offline" ? "status-neutral" : "status-online"}`}
                  >
                    {state}
                  </span>
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
  setStakers,
  countdown,
  onToast,
}: {
  stakers: StakersResponse;
  setStakers: (s: StakersResponse) => void;
  countdown: number;
  onToast: (s: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const total = Object.values(stakers.stakers).reduce((a, b) => a + b, 0);
  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Validator leaderboard"
          detail={`${total} coins staked · next selection in ${countdown}s`}
        />
        <div className="divide-y divide-border">
          {Object.entries(stakers.stakers)
            .sort((a, b) => b[1] - a[1])
            .map(([key, amt], i) => {
              const slashed = key === initialMockData.slashed.creator;
              const chance = total ? Math.round((amt / total) * 100) : 0;
              return (
                <div key={key} className={`p-5 ${slashed ? "bg-destructive/5" : ""}`}>
                  <div className="flex items-center gap-4">
                    <span className="grid h-8 w-8 place-items-center rounded-md bg-muted text-xs font-semibold">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                        {mockPresentation.namesByKey[key]}
                        {key === initialMockData.balance.public_key && (
                          <span className="status status-info">You</span>
                        )}
                        {slashed && (
                          <span className="status status-danger">
                            <AlertTriangle className="h-3 w-3" />
                            Slashed
                          </span>
                        )}
                      </div>
                      <div className="mt-1">
                        <CopyValue value={key} compact />
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`text-base font-semibold ${slashed ? "text-destructive" : ""}`}
                      >
                        {amt} coins
                      </div>
                      <div className="text-xs text-muted-foreground">{chance}% probability</div>
                    </div>
                  </div>
                  <div className="ml-12 mt-3 h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full rounded-full ${slashed ? "bg-destructive" : "bg-primary"}`}
                      style={{ width: `${chance}%` }}
                    />
                  </div>
                </div>
              );
            })}
        </div>
      </section>
      <section className="panel self-start p-5">
        <div className="mb-5">
          <h2 className="text-sm font-semibold">Register stake</h2>
          <p className="mt-1 text-xs text-muted-foreground">Commit coins for the current epoch.</p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const value = Number(amount);
            if (!Number.isFinite(value) || value <= 0) {
              setError("Enter an amount greater than zero.");
              return;
            }
            const result = submitMockStake(stakers, value, initialMockData.balance.balance);
            if (!result.response.ok) {
              setError(result.response.error);
              return;
            }
            setStakers(result.stakers);
            setAmount("");
            setError("");
            onToast(
              `Stake registered. Block selection in ${result.response.creating_block_in_seconds}s.`,
            );
          }}
        >
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
            <span>{initialMockData.balance.balance} coins</span>
          </div>
          {error && (
            <p role="alert" className="mt-3 text-xs text-destructive">
              {error}
            </p>
          )}
          <Button className="mt-5 w-full">
            <Coins /> Register stake
          </Button>
        </form>
      </section>
    </div>
  );
}

function Mempool({
  mempool,
  setMempool,
  onTx,
  onToast,
}: {
  mempool: MempoolResponse;
  setMempool: (m: MempoolResponse) => void;
  onTx: (t: Transaction) => void;
  onToast: (s: string) => void;
}) {
  const [receiver, setReceiver] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <section className="panel overflow-hidden">
        <PanelHeading
          title="Pending transactions"
          detail={`${mempool.transactions.length} transactions awaiting confirmation`}
        />
        <TransactionTable transactions={mempool.transactions} onTx={onTx} />
      </section>
      <section className="panel self-start p-5">
        <h2 className="text-sm font-semibold">Send transaction</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Broadcast from alpha-node to the mempool.
        </p>
        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            const value = Number(amount);
            if (!receiver.trim() || !Number.isFinite(value) || value <= 0) {
              setError("Enter a receiver and a valid amount.");
              return;
            }
            const result = submitMockTransaction(mempool, receiver.trim(), value);
            setMempool(result.mempool);
            setReceiver("");
            setAmount("");
            setError("");
            onToast(`Transaction ${shortKey(result.response.transaction_id, 8, 5)} submitted.`);
          }}
        >
          <div>
            <Label htmlFor="receiver">Receiver</Label>
            <Input
              id="receiver"
              className="mt-2 font-mono text-xs"
              value={receiver}
              onChange={(e) => setReceiver(e.target.value)}
              placeholder="PEM public key or peer name"
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
          <Button className="w-full">
            <Send /> Submit transaction
          </Button>
        </form>
      </section>
    </div>
  );
}
