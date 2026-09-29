import { useState } from "react";
import { ArrowLeft, ArrowRight, Coins, GraduationCap, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { requestFaucet, type Connection } from "@/lib/api-client";

export type TourView = "overview" | "explorer" | "network" | "validators" | "mempool" | "attack_lab";

type Step = {
  title: string;
  view: TourView;
  body: string;
  /** Extra tip shown under the body. */
  tip?: string;
  action?: "faucet";
};

const STEPS: Step[] = [
  {
    title: "Welcome to your node",
    view: "overview",
    body:
      "This console is one node of a Proof-of-Stake blockchain. Everything here comes live from the node you just started; other people's nodes join the same room and talk to yours directly.",
    tip: "This tour takes about two minutes. You can leave any time and it will not block the app.",
  },
  {
    title: "1. Your wallet",
    view: "overview",
    body:
      "Your node created a wallet (a key pair) for you. Coins are not stored anywhere but in the chain, so a new wallet starts at 0. Ask the faucet for 50 free test coins.",
    tip: "They show as pending first: a transaction only counts once it is in a block.",
    action: "faucet",
  },
  {
    title: "2. Send a transaction",
    view: "mempool",
    body:
      "Pick a peer and an amount. Your node signs it with your private key and broadcasts it. Until a block includes it, it waits in the mempool, the waiting room for unconfirmed transactions.",
    tip: "Every node checks your signature and that you actually have the coins, so nobody can spend money they do not have.",
  },
  {
    title: "3. Watch it travel",
    view: "network",
    body:
      "Each node connects straight to the others (a mesh); the signalling server only introduced you. Every transaction, stake and block shows up here as a glowing packet flying from its sender to everyone else.",
    tip: "Drag the nodes around to lay the network out however you like.",
  },
  {
    title: "4. Stake to be eligible",
    view: "validators",
    body:
      "In Proof-of-Stake nobody burns electricity: validators lock up coins as a stake. The more you stake, the bigger your chance of building the next block, and the block reward.",
    tip: "Type an amount in the stake form to see your chance of being picked. Turn on Auto-stake to do this every epoch.",
  },
  {
    title: "5. Why was this node picked?",
    view: "validators",
    body:
      "Scroll to \"Why is this node next?\". The draw is public: every staker gets a slice of a line, a hash of the last block picks one point on it, and that slice's owner builds the block. Every node computes the same answer, so nobody can cheat.",
  },
  {
    title: "6. A block is made",
    view: "explorer",
    body:
      "When the epoch timer ends the picked validator bundles the pending transactions into a block, signs it, and everyone verifies it. Click a block to see its transactions and signatures.",
    tip: "Use the time-travel slider above the chain to replay how the network got here.",
  },
  {
    title: "7. Attack it",
    view: "attack_lab",
    body:
      "Join a second node with \"Join as a malicious node\" ticked: it double-signs conflicting blocks whenever it is elected. Honest nodes spot the two signatures, slash its stake, and mark the block. The Chaos Lab tools can also kill a node, split the network, add latency or censor a recipient.",
    tip: "Slashed blocks turn red in the explorer on every node.",
  },
  {
    title: "That is the whole loop",
    view: "overview",
    body:
      "Wallet, transaction, mempool, stake, election, block, and detection of a cheater. You can re-open this tour any time from the Tour button.",
  },
];

/**
 * Non-blocking guided tour: a small card that walks through the app one view at a time
 * and jumps the dashboard to the right tab for each step.
 */
export function Tutorial({
  connection,
  onNavigate,
  onRefresh,
  onToast,
  onClose,
}: {
  connection: Connection;
  onNavigate: (view: TourView) => void;
  onRefresh: () => void;
  onToast: (message: string) => void;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const step = STEPS[index] ?? STEPS[0]!;
  const last = index === STEPS.length - 1;

  const go = (next: number) => {
    const target = STEPS[next];
    if (!target) return;
    setIndex(next);
    onNavigate(target.view);
  };

  const runAction = async () => {
    setBusy(true);
    try {
      const res = await requestFaucet(connection, 50);
      onToast(res.ok ? "Faucet: 50 test coins requested. They confirm in the next block." : "Faucet request failed.");
      onRefresh();
    } catch (err: any) {
      onToast(err.message || "Faucet request failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label="Guided tour"
      className="fixed bottom-4 right-4 z-50 w-[min(92vw,380px)] rounded-xl border border-primary/30 bg-card p-5 shadow-2xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-primary">
          <GraduationCap className="h-4 w-4" />
          Tour · step {index + 1} of {STEPS.length}
        </div>
        <button
          type="button"
          aria-label="Close tour"
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <h3 className="mt-3 text-base font-semibold">{step.title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
      {step.tip && (
        <p className="mt-2 rounded-md bg-muted/60 p-2 text-xs leading-relaxed text-muted-foreground">
          {step.tip}
        </p>
      )}
      {step.action === "faucet" && (
        <Button className="mt-3 w-full" variant="outline" disabled={busy} onClick={() => void runAction()}>
          <Coins className="h-4 w-4" /> {busy ? "Requesting..." : "Get 50 test coins"}
        </Button>
      )}

      <div className="mt-4 flex gap-1.5">
        {STEPS.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full ${i <= index ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          Skip tour
        </Button>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={index === 0} onClick={() => go(index - 1)}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          <Button size="sm" onClick={() => (last ? onClose() : go(index + 1))}>
            {last ? "Finish" : "Next"} {!last && <ArrowRight className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
