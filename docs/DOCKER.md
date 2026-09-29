# Running with Docker

```
docker compose up -d --build
```

Brings up:
- `signalling` — room-discovery server, port `7000`
- `peer-alice`, `peer-bob` — honest PoS stakers, joined via room `demo`.
  Web API + events websocket published on the host:
  - alice: `http://localhost:6001` (API), `ws://localhost:6002` (events)
  - bob: `http://localhost:6011` (API), `ws://localhost:6012` (events)
- `peer-mallory` — malicious node (`mal_node.py`), also in room `demo`. No
  web API by design (`enable_api` is only true for honest pos peers in
  `start_peer.py`) - see below for how to drive her live.

All four share one Docker network, so this sidesteps the hard "P2P nodes
need public IPs to reach each other" problem entirely - containers reach
each other by service name (`peer-alice`, `signalling`, ...) regardless of
where the whole stack runs. That means this same compose file works
unmodified on a single cloud VM too (rent a box, install Docker, `docker
compose up -d`, done) - no per-node networking work needed, since it's the
same container-to-container networking either way. Only the demo/API ports
need to be reachable from wherever the audience is.

## Get a peer's auth token

```
docker compose logs peer-alice | grep "Auth token"
```

## Driving the malicious node live (demo)

Mallory has no API, so trigger her double-sign via the actual CLI menu.
Compose gives her containers a tty (`tty: true`, `stdin_open: true`)
specifically so this works:

```
docker attach blockchain-simulation-peer-mallory-1
```

Use the menu (option 9 to stake, whatever mal_node.py's malicious flow
requires) to trigger the double-sign. Detach without killing the container
with `Ctrl+P` then `Ctrl+Q` (a plain `Ctrl+C` will send SIGINT to the
container's process).

## Logs / cleanup

```
docker compose logs -f peer-bob     # follow one service
docker compose ps -a                # status of everything
docker compose down                 # stop and remove containers + network
```

## Known gap

Mallory not having a web API means no dashboard visibility into her
directly - the "she got slashed" story is told from an honest peer's
`node_slashed` event (`/events`, see `docs/API.md`), not from her own
state. That's actually the more realistic framing (you learn about the
attacker from the network, not from asking them), but worth knowing going
in - if the demo wants a "villain's-eye view" panel that's more UI work,
not something this backend currently exposes.
