# Web API Contract

The web interface talks to a per-node API server that wraps a running `Peer`
instance. **Implemented**: REST in `webapi/server.py`, push events in
`webapi/events.py`.

A Flask app runs in a background thread; anything that mutates Peer state or
broadcasts a message is bridged onto the Peer's asyncio event loop via
`asyncio.run_coroutine_threadsafe`. Plain reads touch already-existing
Python objects directly.

Enabled automatically for PoS peers (`start_peer.py`) on `peer_port + 1000`
(e.g. peer on 5000 -> API on 6000).

**Auth:** every request needs `Authorization: Bearer <token>`. The token is
generated fresh per process, printed to the peer's console at startup, and
written to `.webapi_token_<port>` next to the process (gitignored - never
commit it). No token or a wrong one gets a 401.

**Binding:** defaults to `127.0.0.1` only. Set env var `WEBAPI_HOST=0.0.0.0`
to expose beyond localhost (e.g. inside a docker container reached only via
a published port) - auth is still required either way.

**Rate limiting & brute-force lockout** (`webapi/rate_limit.py`), shared
between the REST API and `/events`:
- Max 60 requests/minute per client IP - exceeding it gets `429`.
- 5 failed-auth attempts within 60s blocks that IP for 5 minutes - `429` on
  *every* request from it during the block, even with the correct token
  (don't let an attacker keep probing once flagged). Frontend should treat
  `429` as "back off and retry later," not a hard error - show a clear
  message rather than crashing.

## REST Endpoints

### `GET /chain`
Full block list for the chain explorer. Verified shape (actual output of
`Chain.to_block_dict_list()` — note there's no `hash`/`is_valid`/
`slash_creator` field on the wire; `hash` is computed client-side if needed
by hashing the same dict minus `stakers`/`sign`, see `Block.hash` in
`consensus/pos/blockchain_structures.py`).
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
      "sign": "base64"
    }
  ]
}
```

### `GET /peers`
Known peers on the network.
```json
{
  "peers": [
    {"host": "localhost", "port": 5001, "name": "bob", "public_key": "pem"}
  ]
}
```

### `GET /mempool`
Pending (unconfirmed) transactions.
```json
{ "transactions": [ {"id": "uuid", "payload": 5, "sender": "pem", "receiver": "pem", "ts": 1234.5} ] }
```

### `GET /stakers`
Current epoch's registered stakers.
```json
{ "stakers": { "pem-string": 10 }, "epoch_ends_in_seconds": 34 }
```

### `GET /balance`
Caller's own balance (server identifies "self" via its own wallet).
```json
{ "public_key": "pem", "balance": 45 }
```

### `POST /transactions`
Submit a coin transaction from this node's wallet.
```json
// request
{ "receiver": "pem-or-name", "amount": 5 }
// response
{ "ok": true, "transaction_id": "uuid" }
```

### `POST /stakes`
Stake an amount for the current epoch (only valid on staker nodes).
```json
// request
{ "amount": 10 }
// response (success)
{ "ok": true, "creating_block_in_seconds": 34 }
// response (rejected, e.g. already staked / insufficient balance / not a staker)
{ "ok": false, "error": "..." }
```

### `GET /invariants`
Consensus sanity and safety invariants.
```json
{
  "honest_consensus": true,
  "supply_conserved": true,
  "valid_proposers": true,
  "total_blocks": 4,
  "mempool_count": 0,
  "peer_count": 3
}
```

### `POST /malicious/trigger`
Triggers a simulated malicious attack (e.g. double-signing or invalid block proposal) on demand without requiring `docker attach` or CLI menu interaction.
```json
// request
{ "attack_type": "double_sign" }

// response (success)
{
  "ok": true,
  "attack": "double_sign",
  "message": "Malicious double-sign attack triggered. Slashing evidence broadcast to network."
}
```

## WebSocket: `/events` — implemented

Runs on a **separate port**: `api_port + 1` (e.g. REST on 6000 -> events on
6001), because Flask's dev server doesn't speak websocket without extra
dependencies. Implemented in `webapi/events.py`.

**Connect:** `ws://host:6001/events?token=<token>` — same token as the REST
API. Browsers can't set custom headers on a WebSocket handshake, so the
token goes in the query string here instead of an `Authorization` header.
Missing/wrong token closes the connection immediately with code `4401`.

Server pushes JSON messages as node/chain state changes - no request/response,
just keep the connection open and read:

```json
{ "type": "block_appended", "block": { /* same shape as /chain block */ } }
{ "type": "peer_discovered", "peer": { "host": "...", "port": 0, "name": "...", "public_key": "pem" } }
{ "type": "stake_registered", "staker": "pem", "amount": 10 }
{ "type": "node_slashed", "creator": "pem", "block_pos": 3 }
```

Verified live: connected a websocket client, triggered `POST /stakes`,
received the `stake_registered` event within milliseconds.

`node_slashed` is the event to build the malicious-node-detection UI around —
fired whenever `slash_creator` is set true on a block (see
`consensus/pos/p2p.py`, `slash_announcement` handler and `verify_and_slash`).

## Notes for frontend

- All public keys are PEM strings (multi-line) — fine as JSON string values,
  just don't assume single-line.
- Start against mocked responses matching these shapes; swap in the real
  API server once it exists.
