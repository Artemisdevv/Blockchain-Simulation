<div align="center">

<img src="./web/public/favicon.ico" alt="" height="64" />

# Blockchain-Simulation

A multi-node blockchain playground with pluggable consensus (PoW, PoA, PoS), malicious-peer scenarios, and a live web dashboard.

[Overview](#overview) • [Quick start](#quick-start) • [Architecture](#architecture) • [Consensus modes](#consensus-modes) • [Development](#development) • [Documentation](#documentation)


## Overview

Blockchain-Simulation runs a small network of peers in Docker and lets you watch how consensus behaves, including when a node misbehaves. Peers find each other through a lightweight signalling service, then exchange blocks and transactions directly. A web frontend and REST API expose the state of the network.

Highlights:

- **Three consensus implementations**: Proof of Work, Proof of Authority and Proof of Stake, each with its own P2P layer and malicious-node variant.
- **Ready-made cast of peers**: Alice, Bob, a malicious Mallory, and a swarm of extra peers, managed by a peer manager.
- **Signalling server for discovery**: peers register and discover each other without the server handling chain data.
- **Web dashboard**: a TypeScript frontend on port `8080`, with spectator reports and rate-limited API access.
- **Smart contracts**: sandboxed execution with a gas meter.
- **Optional extras**: IPFS integration and persistent storage manager.
- **Demo sharing**: included Windows and Linux/macOS launchers can start the network and expose the frontend through a temporary Cloudflare Quick Tunnel.


## Quick start

### Prerequisites

- Docker Desktop with Docker Compose enabled
- Git
- Python 3.x (only needed to run tests or peers outside Docker)

### Run the demo

#### Windows

```powershell
.\launchers\demo.ps1
```

This builds and starts the complete Docker demo stack, waits for the services to become ready, starts the Cloudflare Quick Tunnel, and opens a separate terminal window displaying the public demo URL. The original terminal continues following Docker Compose logs. Ctrl+Click the URL in the new window to open the demo.

#### Linux / macOS

```bash
chmod +x launchers/demo.sh
./launchers/demo.sh
```

This starts the same Docker demo stack and prints the public Cloudflare Quick Tunnel URL in the current terminal.

The generated Cloudflare URL is temporary and is intended for sharing or presenting a running demo. Cloudflare account credentials, API tokens, and tunnel configuration are not required.

### Run locally using localhost

```bash
cp .env.example .env   # adjust values if needed
docker compose up -d
```

Open the frontend at:

`http://localhost:8080/`

The frontend is available locally without using the public URL. The current default Compose configuration also starts `cloudflared` in the background; the tunnel is not required for local access.

Once the containers are up:

The `peer-*` services below are enabled by the `demo` profile, which both demo launchers activate.

| Service | Port | Purpose |
|---|---|---|
| `frontend` | 8080 | Web dashboard |
| `signalling` | 7000 | Peer discovery |
| `peer-alice`, `peer-bob` | 6000 (inside the network) | Honest peers |
| `peer-mallory` | n/a | Malicious peer for attack scenarios |
| `peer-swarm` | n/a | Extra peers to grow the network |
| `peer-manager` | n/a | Starts and manages peers |
| `cloudflared` | n/a | Public tunnel to the frontend |

> [!TIP]
> Stop and remove everything with `docker compose down`. See [docs/DOCKER.md](docs/DOCKER.md) for container details.

## Architecture

```text
            ┌────────────┐   register / discover   ┌────────────┐
            │  frontend  │                         │ signalling │
            │  (web/)    │                         │  :7000     │
            └─────┬──────┘                         └─────┬──────┘
                  │ REST / events                        │
            ┌─────▼──────┐        direct P2P       ┌─────▼──────┐
            │   webapi   │◄───────────────────────►│   peers    │
            │            │                         │ alice, bob │
            └────────────┘                         │ mallory... │
                                                   └────────────┘
```

## Repository layout

```text
consensus/        PoW, PoA and PoS implementations (chain structures, P2P, malicious nodes)
signalling/       Signalling server, client and healthcheck
webapi/           Flask API: events, rate limiting, healthcheck
smart_contract/   Contract storage, gas metering and sandboxed execution
storage/          Storage manager
ipfs/             IPFS helper
web/              Frontend (TypeScript, Vite)
tests/            Test suite
docs/             API, Docker and frontend UX docs
peer_manager.py   Peer lifecycle management
start_peer.py     Peer entry point
launchers/        One-command demo launchers for Windows and Linux/macOS
```

## Consensus modes

| Mode | Directory | Notes |
|---|---|---|
| Proof of Work | `consensus/pow/` | Nodes compete to produce blocks |
| Proof of Authority | `consensus/poa/` | Approved validators produce blocks |
| Proof of Stake | `consensus/pos/` | Validators are chosen based on stake; includes a `malicious_peer.py` for attack scenarios |

Each mode ships a `mal_node.py` so you can observe how the network reacts to a faulty or hostile participant.

## Development

Install dependencies and run the tests:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests/
```

The test suite covers, among other things, PoS bug fixes, election details, staking, genesis balances, empty blocks, the peer manager, rate limiting and spectator reports.

To work on the frontend:

```bash
cd web
npm install
npm run dev
```

## Documentation

- [API reference](docs/API.md)
- [Docker setup](docs/DOCKER.md)
- [Frontend UX notes](docs/FRONTEND_UX.md)
