import { Dices } from "lucide-react";
import type { StakersResponse } from "./mock-data";
import { shortKey } from "./utils";

const SEGMENT_TINTS = [
  "bg-primary/25",
  "bg-success/25",
  "bg-warning/30",
  "bg-destructive/20",
  "bg-muted-foreground/25",
];

/**
 * "Why was this node picked?": shows the stake-weighted draw the backend runs
 * (elect_leader). Stakers get slices of a line as long as the total stake, in public-key
 * order; sha256(seed) mod total is a point on that line; whoever owns that slice leads.
 */
export function ElectionExplainer({
  stakers,
  getName,
  selfPk,
}: {
  stakers: StakersResponse;
  getName: (pk: string) => string;
  selfPk: string;
}) {
  const election = stakers.election;
  const empty = !election || election.total <= 0 || election.pick === null;

  return (
    <section className="panel overflow-hidden">
      <div className="flex items-start gap-3 border-b border-border px-6 py-4">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Dices className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-semibold">Why is this node next?</h2>
          <p className="text-xs text-muted-foreground">
            The draw is public and repeatable: every node runs the same maths on the same data.
          </p>
        </div>
      </div>

      {empty ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          Nobody has staked this epoch yet. Stake some coins to enter the draw.
        </div>
      ) : (
        <div className="space-y-5 p-6">
          <div>
            <div className="relative pt-6">
              <div
                className="absolute top-0 -translate-x-1/2 text-center text-[10px] font-semibold text-primary"
                style={{ left: `${(election.pick! / election.total) * 100}%` }}
              >
                pick {election.pick}
                <div className="mx-auto h-0 w-0 border-x-[5px] border-t-[6px] border-x-transparent border-t-primary" />
              </div>
              <div className="flex h-12 overflow-hidden rounded-lg border border-border">
                {election.ranges.map((range, i) => {
                  const isLeader = range.staker === election.leader;
                  return (
                    <div
                      key={range.staker}
                      title={`${getName(range.staker)}: coins ${range.start}-${range.end - 1}`}
                      className={`flex min-w-0 flex-col items-center justify-center border-r border-background px-1 text-center text-[11px] last:border-r-0 ${
                        SEGMENT_TINTS[i % SEGMENT_TINTS.length]
                      } ${isLeader ? "ring-2 ring-inset ring-primary font-semibold" : ""}`}
                      style={{ width: `${(range.amount / election.total) * 100}%` }}
                    >
                      <span className="w-full truncate">{getName(range.staker)}</span>
                      <span className="text-muted-foreground">{range.amount}</span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>0</span>
                <span>{election.total} coins staked</span>
              </div>
            </div>
          </div>

          <ol className="space-y-3 text-sm">
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">1</span>
              <span>
                <span className="font-medium">Shared seed.</span> The seed is the hash of the last finalized
                block (<span className="font-mono text-xs">{shortKey(election.seed, 8, 6)}</span>). Every node
                has the same chain, so every node has the same seed.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">2</span>
              <span>
                <span className="font-medium">Stake is your share of the line.</span> Stakers are laid end to end
                in public-key order on a line {election.total} coins long, so a bigger stake means a bigger slice.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">3</span>
              <span>
                <span className="font-medium">One point decides.</span> sha256(seed) mod {election.total} ={" "}
                <span className="font-mono">{election.pick}</span>, and that point lands in{" "}
                <span className="font-semibold text-primary">
                  {election.leader
                    ? election.leader === selfPk
                      ? "your"
                      : `${getName(election.leader)}'s`
                    : "nobody's"}
                </span>{" "}
                slice, so {election.leader === selfPk ? "you build" : "they build"} the next block. The
                same inputs give the same answer on every node, so nobody can pick themselves or disagree.
              </span>
            </li>
          </ol>
        </div>
      )}
    </section>
  );
}
