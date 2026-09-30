# Frontend Guide

The dashboard (`web/`) is Vite + React + TypeScript + Tailwind + shadcn/ui (TanStack Start). It is one node's
view of a Proof-of-Stake network: you start a node from the browser, and everything on screen comes live from
that node's [web API](API.md).

## The flow

1. **Join screen** (`ConnectionScreen.tsx`): enter a *node name* and a *room ID*. The peer manager starts a real
   peer for you and the dashboard connects to it. Optional: *Join as a malicious node*. *Advanced: connect by URL*
   points the dashboard at any existing node with its token (used for spectators and the demo peers).
2. **Dashboard** (`Dashboard.tsx`): live updates arrive over the node's `/events` WebSocket
   (`block_appended`, `peer_discovered`, `peer_left`, `stake_registered`, `tx_seen`, `node_slashed`,
   `attack_state`, `resync_started`, `chain_replaced`); a 30 second REST refresh backs them up.
   Toasts name the node involved: who won a block, which validator was slashed. When a node finds it is on a
   different branch (after a double-sign) it shows "Out of sync ... requesting chains" and, once it has switched,
   "Fork resolved: switched to the network chain (6 → 7 blocks)". If the peer disappears (manager restarted, idle
   timeout) the dashboard returns to the join screen instead of showing zeros.

**+50 Test Coins** only queues a faucet transaction: the coins arrive with the next block (the toast says how long),
and the button reads "Coins pending..." until then. The mempool, pending balance and stake-adjusted balance update as
soon as a transaction or stake is seen, not only on the 30 second refresh.

Header actions: **Tour**, **Share spectator link**, **Auto-stake** switch, **+50 Test Coins**, **Send
transaction**, **Add stake**. They wrap onto several lines on narrow screens.

## Views

| Tab | What it shows |
|---|---|
| **Overview** | Balance (with pending and auto-faucet share), epoch countdown, peer count, chain height, pending txs, live invariants, latest blocks, stake distribution, mempool |
| **Explorer** | The chain as block cards, newest first. Each block shows its creator, transactions, stake and a Verified / **Slashed** badge read from the chain (`is_valid`, `slash_creator`). **Time travel**: a slider, *Replay from start* and *Back to live* replay how the chain grew; new blocks keep arriving while you look back. Click a block or transaction for the details. The confirmed-transactions table below is paged (8 per page, newest first) |
| **Network** | Peer mesh topology. Drag nodes to rearrange. A **Genesis** (faucet) node sits in the middle: faucet coins fly from it to the requesting node. A transfer (blue) flies from sender to receiver; stakes (amber) and new blocks (green) fly from the staker or winner to every other node. Known peers list below |
| **Validators** | Leaderboard with each staker's win probability, the stake form (shows your chance of being picked as you type), and **Why is this node next?**: the stake-weighted draw drawn as slices of a line with the hash "pick" marked, plus who won the last epoch |
| **Mempool** | Pending transactions (paged, 8 per page) and the send form (receiver is a peer name) |
| **Chaos Lab** | Fault injection on your own node: kill a managed node (only nodes in your room are listed), partition the network, add outbound latency, censor a recipient. Shows the malicious nodes currently running. While any fault is active a **Chaos active on this node** banner appears on every tab, and with latency on, your own packets wait at your node for that long before they fly |

## Roles and attacks

- **Malicious node** (join-screen option): stakes automatically and double-signs conflicting blocks whenever it
  is elected. Honest nodes detect the pair, mark the block **Slashed** on every dashboard, and take the stake.
  The Validators tab shows "Last epoch's winner ... Slashed for double-signing". The two blocks put honest nodes
  on different branches; each node that notices asks its peers for chains at once and switches to the heavier one.
- **Chaos Lab** controls are deliberate faults for demonstrating resilience, not attacks on the network.

## Spectator mode

**Share spectator link** creates a read-only link (24 hours) for your room, with a QR code. Anyone who opens it
sees the dashboard without a node and cannot send transactions or change anything. Spectators can export a
**PDF run report** of the room (participants, blocks, stakes, attack events). Creating a link needs a token from
a node in the room, so it is done from the dashboard, not the join screen.

## Guided tour

The **Tour** button (it also opens once for a new browser) walks through wallet, transaction, network, staking,
the election, blocks and the malicious-node flow, jumping to the right tab at each step.

## Suggested demo (about 3 minutes)

1. Two browsers (or a laptop and a phone via the spectator QR) join the same room by typing a room ID: no IPs.
   The Network tab shows them connect.
2. Get test coins, stake, send a transaction. Watch the packet fly, the mempool entry, then the block land.
3. Open **Why is this node next?** and explain the draw.
4. Join a node as **malicious**. It double-signs when elected; the block turns **Slashed** on every dashboard.
5. Use the **Chaos Lab** to partition and heal, or kill a node.
6. Drag the **time-travel** slider back over the whole run.

Keep **Auto-stake** on for one node only; with several auto-stakers a node can occasionally fall a block behind.

## Development

```
cd web
npm install
npm run dev        # http://localhost:8080
```

The dev server proxies `/api/peer-setup`, `/api/runtime` and `/ws/runtime` to the peer manager
(`localhost:7001` / `7002` by default) and `/api/alice`, `/api/bob` to the demo peers. Those ports are not
published by `docker-compose.yml` by default, so the simplest workflow is to run everything in Docker and rebuild
the frontend after changes:

```
docker compose up -d --build frontend
```

Source layout: `src/features/blockchain/` (Dashboard, ConnectionScreen, Explorer pieces, ElectionExplainer,
SpectatorShare, Tutorial), `src/lib/api-client.ts` (typed API + WebSocket client), `src/routes/` (pages).
