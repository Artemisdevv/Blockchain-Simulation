# Frontend UX & Demo Plan

For Shreyas (build) and Adarsh (UX test + demo script). Goal: not just
"functional dashboard" — something that visibly *pops* on a judge's screen
in the 2-3 minutes they'll actually watch.

## Base flow

1. **Connect screen** (one-time, store in localStorage): node API URL
   (`http://localhost:6000`) + the auth token printed when the peer starts.
   This is not a login system — it's just pointing the dashboard at your own
   local node. See `docs/API.md` for the auth header format.
2. **Dashboard** — subscribe to `/events` (see `docs/API.md`) for live push
   updates (`block_appended`, `peer_discovered`, `stake_registered`,
   `node_slashed`); fall back to polling `/chain`, `/peers`, `/mempool`,
   `/stakers` only if you need data `/events` doesn't cover:
   - Overview: my balance, epoch countdown, peer count
   - Chain explorer, live peer list, stakers panel, send-tx form, stake form

That's the functional floor. Below is what turns it into something that
stands out.

## Why "wow factor" here specifically

PS3's own bonus list basically hands you the demo script: *network/blockchain
visualizations, real-time monitoring, malicious-node detection, validator
dashboards, fault tolerance, network stats.* Lean into exactly those — a
judge who wrote that list will recognize when a team actually built it.

## Tier 1 — build these, highest impact per hour

**1. Dark, purpose-built visual design, not a default Bootstrap table.**
Cheapest thing on this list and the biggest multiplier on perceived quality.
Dark background, monospace for hashes/pubkeys (truncate + copy-to-clipboard,
nobody wants to read a full PEM key), one accent color reserved for "this is
me" (my node, my stake, my transaction). A generic admin-table UI reads as
unfinished next to this even with identical functionality underneath.

**2. Chain explorer as connected block cards, not a table.**
Each block a card (creator name/truncated key, tx count, timestamp,
staked_amt). Draw a visible link from each card back to the block whose hash
matches its `prevHash` — literally show the chain. New block arrives (poll
detects `/chain` grew) → animate it sliding in. This is the single most
recognizable "yes, this is a blockchain" visual and it's just CSS + a poll
diff, not a new backend feature.

**3. Live validator/stakers leaderboard with probability bars.**
`GET /stakers` gives you `{pem: amount}`. Render each as a bar sized by
`amount / sum(all amounts)` — that bar *is* their literal win probability
for the next block (that's the actual PoS mechanic you fixed in #3). When a
block lands, flash/highlight whichever staker turns out to be the creator.
Shows judges you understand the mechanism you were debugging, not just that
you copy-pasted a UI over it.

**4. Live peer topology graph.**
`GET /peers` → force-directed graph (nodes = peers, you at center or
highlighted). A library like `react-force-graph` or a small D3 force sim
gets you this in an afternoon. Watching the mesh reshape as nodes join is a
strong visual, and it's a direct payoff of the signalling-server work (#4) —
frame it as "nodes finding each other with just a room code, no manual IPs."

**5. The malicious-node moment — build the demo around this.**
The repo already ships `mal_node.py` for each consensus type, and the
slashing bug we found and fixed (#3 — `verify_and_slash` was checking a
signature against the wrong block's content, and duplicating evidence in the
broadcast) directly enables this. Live demo sequence:
  - Start 2-3 honest nodes + 1 malicious node (`mal_node.py`, double-signs)
  - Dashboard shows the malicious node's stake in the leaderboard like
    everyone else — nothing looks wrong yet
  - It double-signs → other nodes broadcast `slash_announcement` → dashboard
    flashes that block/node red, banner: **"Node X slashed — double-sign
    detected"**, its stake zeroes out on screen
  This is a genuine security mechanism firing live, not a canned animation.
  It's the strongest "wow" available because it's real, not staged, and
  judges can ask questions about it and get real answers.

## Tier 2 — stretch, do these only if Tier 1 is solid with time to spare

- **Room-join flourish**: show the room ID as a big shareable code (maybe a
  QR code) on the connect screen — "anyone scans this to join your network
  instantly," ties back to the signalling server story.
- **Transaction flow micro-animation**: small element moves from a "pending"
  mempool list into the block card that confirms it.
- **Fault-tolerance live-kill demo**: kill a connected peer mid-demo, show
  the topology graph self-heal as gossip sampling reconnects (`#4`'s
  discover_peers/gossip_peer_sampler already does this automatically — no
  new backend work, just show it happening).
- **Consensus health tiles**: animated epoch countdown, blocks/minute,
  total chain weight (sum of all stakes ever) as a running number.

## Suggested demo narrative (~90 seconds)

1. Two terminals join the same room by typing a room ID — no IPs. Topology
   graph shows them connect.
2. Stake, send a transaction, watch the leaderboard bar predict who's about
   to win, watch the block card slide into the chain.
3. Bring in a malicious node. It double-signs. Dashboard catches it live,
   flashes red, explains what just happened in one line of UI text.
4. One line to judges: "this consensus had bugs when we started — here's the
   actual exploit it would have missed" (ties back to issue #3's writeup).

That last beat is what separates this from every other team's dashboard:
you're not just showing a UI, you're showing a security fix working.

## Data already available (no backend work needed for Tier 1)

See `docs/API.md` for full shapes. Everything above only needs:
`GET /chain`, `GET /peers`, `GET /stakers`, `GET /mempool`.
