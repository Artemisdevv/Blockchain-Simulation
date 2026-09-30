# Web API

There are two HTTP surfaces:

1. **Per-node API** (`webapi/server.py`, `webapi/events.py`): one per running PoS peer. Reads that peer's
   chain/mempool/stakers, and lets you send transactions, stake and drive the Chaos Lab.
2. **Peer manager API** (`peer_manager.py`): one per Compose stack. Starts and stops peers for the
   browser, mints read-only spectator links, and proxies the per-node APIs so the browser only talks to one
   origin.

The web dashboard uses (2) to start your node and then talks to that node's API (1) through the peer
manager's proxy.

---

## 1. Per-node API

A Flask app runs in a background thread next to the peer; anything that mutates peer state or
broadcasts is bridged onto the peer's asyncio loop with `asyncio.run_coroutine_threadsafe`. Plain reads
touch existing Python objects directly.

Enabled for every PoS peer, honest or malicious (`start_peer.py`), on `peer_port + 1000`
(peer on 5000 -> API on 6000, events on 6001).

**Auth.** Every request needs `Authorization: Bearer <token>`; anything else gets `401`.
The token is `WEBAPI_TOKEN` if set (the Compose demo peers use `demo-token-alice`, `demo-token-bob`),
otherwise generated per process. It is printed at startup and written to `.webapi_token_<port>`
(gitignored, never commit it).

**Binding.** `127.0.0.1` by default. Set `WEBAPI_HOST=0.0.0.0` to expose it (the peer Docker image and the
peer manager do; auth is still required). `WEBAPI_CORS_ORIGINS` (comma separated) lists browser origins
allowed to call the API directly; the default is localhost only.

**Rate limiting** (`webapi/rate_limit.py`), shared by REST and `/events`:
- 300 requests per minute per client IP, then `429`.
- 5 failed-auth attempts within 60s blocks that IP for 5 minutes (`429` on every request during the block,
  even with the right token).
- `POST /faucet` has its own limit: 10 requests per hour per IP.

### Chain and network state

#### `GET /chain`
Every block, oldest first. `?height=N` returns only the first `N+1` blocks (used by the time-travel scrubber).
```json
{
  "blocks": [
    {
      "id": "uuid",
      "prevHash": "hex-or-null",
      "ts": 1234567890123,
      "creator": "pem-string",
      "staked_amt": 10,
      "files": {},
      "transactions": [
        {"id": "uuid", "payload": 5, "sender": "pem", "receiver": "pem", "ts": 1234.5, "sign": "base64"}
      ],
      "stakers": [
        {"id": "uuid", "staker": "pem", "amt": 10, "ts": 1234.5, "sign": "base64"}
      ],
      "vrf_proof_b64": "base64",
      "seed": "hex",
      "sign": "base64",
      "is_valid": true,
      "slash_creator": false
    }
  ]
}
```
`is_valid` is `false` and `slash_creator` is `true` once a block has been slashed for double-signing.
The dashboard reads slashing from these fields, so it is the same on every node.

#### `GET /peers`
Peers this node knows about, **including itself**.
```json
{ "peers": [ {"host": "peer-bob", "port": 5000, "name": "bob", "public_key": "pem"} ] }
```

#### `GET /mempool`
Pending (unconfirmed) transactions.
```json
{ "transactions": [ {"id": "uuid", "payload": 5, "sender": "pem", "receiver": "pem", "ts": 1234.5} ] }
```

#### `GET /stakers`
This epoch's registered stakers plus the data behind the leader election.
```json
{
  "stakers": { "pem-string": 10 },
  "epoch_ends_in_seconds": 34,
  "election": {
    "seed": "hash of the last finalized block",
    "total": 40,
    "pick": 17,
    "leader": "pem-string",
    "ranges": [ {"staker": "pem", "amount": 10, "start": 0, "end": 10} ]
  }
}
```
`election` is `null` before the chain exists; with no stakers `total` is 0 and `pick`/`leader` are `null`.
See [How the leader is chosen](#how-the-leader-is-chosen).

#### `GET /balance`
This node's own wallet.
```json
{ "public_key": "pem", "balance": 45, "pending_income": 50, "auto_faucet_pending": 50 }
```
`balance` is confirmed coins minus this epoch's stake (never negative unless slashed). `pending_income` is
coins addressed to this wallet that are still in the mempool. `auto_faucet_pending` is the part of that from
the one-time auto-stake faucet request.

#### `GET /metrics`
```json
{ "blocks_count": 4, "total_transactions": 6, "total_staked": 40, "mempool_count": 0,
  "peer_count": 3, "avg_block_time_sec": 60.0, "room_id": "demo" }
```

#### `GET /invariants`
Cheap consistency checks computed from this node's chain.
```json
{ "honest_consensus": true, "supply_conserved": true, "valid_proposers": true,
  "total_blocks": 4, "mempool_count": 0, "peer_count": 3 }
```
- `honest_consensus`: every block's `prevHash` equals the hash of the block before it.
- `supply_conserved`: coins minted (genesis grant, faucet, 6 per block) minus slashed stake equals the sum of
  all wallet balances.
- `valid_proposers`: every non-genesis block's signature verifies against its claimed `creator`. It does not
  re-derive the elected leader (nodes reject non-elected creators when a block arrives).

### Actions

#### `POST /transactions`
Send coins from this node's wallet. `receiver` is a discovered peer **name** or a full PEM public key.
```json
// request
{ "receiver": "bob", "amount": 5 }
// response
{ "ok": true, "transaction_id": "uuid" }
// errors (400 / 409): unknown peer, non-positive amount, insufficient balance, chain not initialized
{ "ok": false, "error": "insufficient balance" }
```

#### `POST /stakes`
Stake for the current epoch (staker nodes only). Allowed only in the first 5/6 of the epoch and once per
epoch; needs `amount <= balance`.
```json
// request
{ "amount": 10 }
// success
{ "ok": true, "creating_block_in_seconds": 34 }
// rejected (400): not a staker, already staked, insufficient balance, registration closed, bad amount
{ "ok": false, "error": "..." }
```

#### `GET /auto_stake`, `POST /auto_stake`
Auto-stake stakes half of the spendable balance each epoch (and asks the faucet once if the node has no coins).
Off by default for honest nodes, on for malicious ones. `available` is `false` on non-staker nodes.
```json
// GET response / POST response
{ "enabled": false, "available": true }
// POST request
{ "enabled": true }
```

#### `POST /faucet`
Test coins for demos: a faucet-signed mint to this node, broadcast to the mempool (confirmed in the next
block). Amount `1..500`, default 50.
```json
// request
{ "amount": 50 }
// response
{ "ok": true, "added_amount": 50, "new_balance": 0, "transaction_id": "uuid" }
```

### Chaos Lab

These act on **this** node only.

| Route | Body | Effect |
|---|---|---|
| `GET /attack-lab/state` | | `{"blocked_peers": [pem], "latency_ms": 0, "censored_receivers": [pem]}` |
| `POST /attack-lab/partition` | `{"peer_keys": [pem, ...]}` | Cut this node's links to those known peers |
| `POST /attack-lab/heal-partition` | | Restore them |
| `POST /attack-lab/latency` | `{"latency_ms": 1500}` (0-10000) | Delay this node's outbound broadcasts |
| `POST /attack-lab/censorship` | `{"receiver": "name-or-pem", "enabled": true}` | Reject transactions to that receiver |

#### `POST /malicious/trigger`
A **simulation**, not a real attack: marks this node's newest block invalid/slashed and broadcasts slashing
evidence for it, so every node marks it slashed. Body `{"attack_type": "double_sign"}` (ignored; only this
behaviour exists). To see a real double-sign detected, join a node with the **malicious role** (below).
```json
{ "ok": true, "attack": "double_sign", "target_block_pos": 3,
  "message": "Malicious double-sign attack triggered. Slashing evidence broadcast to network." }
```

### WebSocket `/events`

A **separate port**: `api_port + 1` (REST 6000 -> events 6001). Connect with
`ws://host:6001/events?token=<token>` (browsers cannot set headers on a WebSocket handshake, so the token is a
query parameter). A missing or wrong token closes with code `4401`; rate limiting closes with `4429`.
The server only pushes JSON, nothing needs to be sent:

```json
{ "type": "block_appended", "block": { /* same shape as a /chain block */ } }
{ "type": "peer_discovered", "peer": { "host": "...", "port": 0, "name": "...", "public_key": "pem" } }
{ "type": "peer_left", "peer": { "host": "...", "port": 0, "name": "..." } }
{ "type": "stake_registered", "staker": "pem", "amount": 10 }
{ "type": "tx_seen", "sender": "pem-or-Genesis", "receiver": "pem", "amount": 5 }
{ "type": "node_slashed", "creator": "pem", "block_pos": 3 }
{ "type": "attack_state", "attack": "partition|latency|censorship", "...": "..." }
```
`tx_seen` fires when a transaction enters this node's mempool (drives the packet animation). `node_slashed`
fires when a block is marked slashed (see `slash_announcement` and `verify_and_slash` in `consensus/pos/p2p.py`).

---

## 2. Peer manager API

`peer_manager.py`, port `7001` (HTTP) and `7002` (WebSocket proxy) inside the Compose network. The frontend
reaches it through `/api/peer-setup/...`, `/api/runtime/...` and `/ws/runtime/...` on port 8080.

| Route | Auth | Purpose |
|---|---|---|
| `POST /peers` | none | Start a peer. Body `{"name", "room_id", "role"}`; `role` is `honest` (default) or `malicious`. Returns `{peer_id, name, room_id, role, token}` (201). Names: 1-32 of `A-Za-z0-9_-`, room ids up to 64. At most 9 managed peers (`503` when full); names are unique among running peers |
| `GET /peers` | none | List managed peers `{peer_id, name, room_id, role}` (no tokens) |
| `DELETE /peers/<peer_id>` | `Bearer` token of any live peer **in the same room** | Stop a peer (a node can stop itself; Chaos Lab "Kill" stops a room-mate). `403` otherwise |
| `/api/runtime/<peer_id>/<path>` | the peer's own token | Proxy to that peer's per-node API |
| `/ws/runtime/<peer_id>/events` | `?token=` | Proxy to that peer's `/events` |
| `POST /spectator-links` | `Bearer` token of a peer in the room | Mint a read-only 24h spectator token for **that peer's room** (the body is ignored) |
| `/spectator/<token>/<path>` | `Bearer <token>` | Read-only proxy (`chain`, `peers`, `mempool`, `stakers`, `metrics`, `invariants`, `attack-lab/state`) |
| `/spectator/<token>/report.json`, `report.pdf` | `Bearer <token>` | Run report (JSON or PDF) for the room |

Managed peers are stopped after `PEER_MANAGER_IDLE_TIMEOUT` (default 120s) without any dashboard traffic, and
their ports are reused.

### Roles

- **honest**: stakes when told to (or via auto-stake), mints blocks when elected.
- **malicious** (`consensus/pos/malicious_peer.py`): stakes automatically. When elected it mints **two
  conflicting blocks** on the same parent (paying 75% / 50% of its balance to different peers) and sends each
  to half of its connections. Honest nodes detect the double-sign, slash the block and its creator's stake,
  and broadcast the evidence.

---

## How the leader is chosen

Deterministic; every node computes the same result from shared data (`elect_leader` in
`consensus/pos/blockchain_structures.py`):

1. `seed` = hash of the last finalized block.
2. Stakers are laid end to end in **public-key order** on a line `total_stake` coins long.
3. `pick = sha256(seed) mod total_stake`. The staker whose range `[start, end)` contains `pick` is the leader.

A node rejects a block whose creator is not the leader that the block's signed stake list elects, or whose
stake list omits or alters a stake it already knows. `/stakers` returns exactly these numbers.

## Notes

- All public keys are PEM strings (multi-line); do not assume single-line.
- Blocks with zero transactions are valid: a block is minted every epoch even when the mempool is empty.
