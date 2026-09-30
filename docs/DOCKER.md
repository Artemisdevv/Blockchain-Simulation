# Running with Docker

```
docker compose up -d --build
```

The project shows up in Docker Desktop as **blockchain-simulation** (set with `name:` in
`docker-compose.yml`, not derived from the folder name).

## What starts

| Service | Started by | Purpose |
|---|---|---|
| `frontend` | `docker compose up` | Web dashboard on **http://localhost:8080** (also proxies the peer manager and the demo peers) |
| `signalling` | `docker compose up` | Room-discovery server, port `7000` |
| `peer-manager` | `docker compose up` | Starts the peers you create from the join screen. Keeps up to nine at a time (`PEER_MANAGER_MAX_PEERS`); idle peers are stopped after 120s, and closing a node's dashboard with the Disconnect button stops it immediately |
| `cloudflared` | `docker compose up` | Cloudflare Quick Tunnel to the frontend, for a public demo URL (see the launchers in the README) |
| `peer-alice`, `peer-bob` | `--profile demo` | Named honest PoS stakers in room `demo` |
| `peer-mallory` | `--profile demo` | A malicious PoS peer in room `demo` |
| `peer-swarm` | `--profile demo` | Anonymous, scalable filler peers (non-stakers) |

The four `peer-*` services are **opt-in** so a fresh `docker compose up` starts with an empty network: the
first person to join a room creates it, and later joiners connect to them. Start the scripted demo cast with:

```
docker compose --profile demo up -d --build
```

`launchers/demo.ps1` and `launchers/demo.sh` start the stack **without** the demo peers (an empty network) and print
the public tunnel URL. Add `-DemoPeers` (PowerShell) or `--demo-peers` (shell) to include the scripted cast. Starting
a launcher without the flag first removes any demo peers left over from an earlier run.

## Joining from the browser

Open http://localhost:8080, enter a **node name** and a **room ID**, and press *Start PoS Peer*. The peer manager
starts a real `start_peer.py` process for you (`ACTION=room`) and the dashboard connects to it. Tick
**Join as a malicious node** to start the node with the malicious role instead (it stakes automatically and
double-signs when elected; see `docs/API.md`).

- The first node in a room creates the network and holds the genesis coins; later nodes bootstrap off peers
  the signalling server returns for that room.
- Honest nodes start with **auto-stake off**; there is a switch in the dashboard header.
- A new wallet is generated every time a managed node starts, so disconnecting and rejoining gives a new
  identity (and a zero balance).

## Demo peers and their ports

With `--profile demo`, the honest peers' web API and events socket are published on the host:

- alice: `http://localhost:6001` (API), `ws://localhost:6002` (events), token `demo-token-alice`
- bob: `http://localhost:6011` (API), `ws://localhost:6012` (events), token `demo-token-bob`

`peer-mallory` runs the same malicious role as the join-screen option, with auto-stake on so it enters the
election by itself (its web API exists but is only reachable inside the Compose network). Connect the dashboard
to alice or bob with `http://localhost:8080/?node=alice` (or `?node=bob`), or with *Advanced: connect by URL* on
the join screen; the join form itself only creates new peers.

Auth tokens are printed at startup if you need them:

```
docker compose logs peer-alice | grep "Auth token"
```

The demo peers keep their wallet and chain in the container (`DISK_LOAD` / `DISK_SAVE`), so they survive a
`docker compose restart` but not `docker compose down`. Run reports from the peer manager are stored in the
`peer-manager-reports` volume.

## Networking

All services share one Docker network, so peers reach each other by service name (`peer-alice`, `signalling`, ...)
no matter where the stack runs. That sidesteps the "P2P nodes need public IPs" problem, and the same Compose file
works unmodified on a single cloud VM. Only the frontend port (8080) needs to be reachable by the audience.

## Scaling to more nodes

`alice`/`bob`/`mallory` are fixed named services (the demo story needs named characters). For anonymous filler
nodes there is `peer-swarm`, with no fixed name or published ports:

```
docker compose --profile demo up -d --scale peer-swarm=10
```

Each replica auto-detects and advertises its own container IP (`AUTO_DETECT_HOST=true`, see `detect_own_ip()` in
`start_peer.py`) rather than a shared hostname, and duplicate names are renamed by the app (`swarm`, `swarm1`,
...). Swarm peers are non-stakers, so they do not take part in block production.

## Logs / cleanup

```
docker compose logs -f peer-manager           # managed peers' output (browser-created nodes)
docker compose logs -f peer-bob               # one demo service
docker compose ps -a                          # status of everything
docker compose down                           # stop and remove containers + network
docker compose down -v                        # ... and the run-report volume
```

## Rebuilding after code changes

The frontend and peers run from images built at `--build` time; the source is not mounted. After changing code:

```
docker compose up -d --build frontend peer-manager
```

Rebuilding `peer-manager` stops every peer it started, so join again afterwards.
