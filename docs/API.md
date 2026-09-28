# Web API Contract

The web interface talks to a per-node API server that wraps a running `Peer`
instance. This is a design doc for the API shape — implementation is a
separate task (see issue referenced in the PR that adds this file).

Run one API server alongside each `Peer` (same asyncio event loop, so it can
read `Peer` / `Chain.instance` state directly without cross-thread locking).
Suggested port convention: `peer_port + 1000` (e.g. peer on 5000 -> API on 6000).

## REST Endpoints

### `GET /chain`
Full block list for the chain explorer.
```json
{
  "blocks": [
    {
      "id": "uuid",
      "prevHash": "hex",
      "hash": "hex",
      "ts": 1234567890123,
      "creator": "pem-string",
      "staked_amt": 10,
      "transactions": [
        {"id": "uuid", "payload": 5, "sender": "pem", "receiver": "pem", "ts": 1234.5}
      ],
      "stakers": [
        {"id": "uuid", "staker": "pem", "amt": 10, "ts": 1234.5}
      ],
      "is_valid": true,
      "slash_creator": false
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
// response
{ "ok": true }
```

## WebSocket: `/events`

Server pushes JSON messages as node/chain state changes, for live dashboard
updates without polling.

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
