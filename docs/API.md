# Web API Contract

The web interface talks to a per-node API server that wraps a running `Peer`
instance. **Implemented** in `webapi/server.py` (REST only — `/events`
websocket below is still just a design sketch, not built yet).

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

## WebSocket: `/events` — NOT YET IMPLEMENTED

Design sketch only. For now, poll `/chain`, `/peers`, `/mempool`, `/stakers`
on an interval (e.g. every 2-3s) for live-ish updates. Server pushes below
are the intended shape once someone builds this.

```json
{ "type": "block_appended", "block": { /* same shape as /chain block */ } }
{ "type": "peer_discovered", "peer": { "host": "...", "port": 0, "name": "...", "public_key": "pem" } }
{ "type": "stake_registered", "staker": "pem", "amount": 10 }
{ "type": "node_slashed", "creator": "pem", "block_pos": 3 }
```

`node_slashed` is the event to build the malicious-node-detection UI around —
fired whenever `slash_creator` is set true on a block (see
`consensus/pos/p2p.py`, `slash_announcement` handler and `verify_and_slash`).

## Notes for frontend

- All public keys are PEM strings (multi-line) — fine as JSON string values,
  just don't assume single-line.
- Start against mocked responses matching these shapes; swap in the real
  API server once it exists.
