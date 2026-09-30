<div align="center">

<img src="./web/public/favicon.ico" alt="Blockchain Simulation" height="64" />

# Blockchain-Simulation

**A multi-node blockchain simulation for exploring consensus, peer-to-peer communication, and malicious-node behaviour.**

Proof of Work • Proof of Authority • Proof of Stake

[Overview](#overview) • [Quick Start](#quick-start) • [Architecture](#architecture) • [Consensus](#consensus) • [Development](#development) • [Documentation](#documentation)

</div>

---

## Overview

**Blockchain-Simulation** is an interactive blockchain playground that runs a small network of peers in Docker.

Peers discover one another through a lightweight signalling service and then communicate directly to exchange blocks and transactions. A web dashboard and REST API provide a live view of the running network.

The project is designed for **experimentation and demonstration**: switch between consensus mechanisms, observe peer behaviour, and introduce malicious nodes to explore how the network responds.

### What's Included

| Component | Description |
|---|---|
| **Proof of Work** | Nodes compete to produce blocks |
| **Proof of Authority** | Approved validators produce blocks |
| **Proof of Stake** | Validators are selected according to stake |
| **Peer Network** | Alice, Bob, Mallory, and additional swarm peers |
| **Signalling Service** | Lightweight room-based peer discovery |
| **Web Dashboard** | Live network state and spectator reports |
| **Smart Contracts** | Sandboxed execution with gas metering |
| **Storage / IPFS** | Optional persistence and IPFS integration |
| **Public Demo** | Cloudflare Quick Tunnel through the included launchers |

---

## Quick Start

### Prerequisites

- Docker Desktop with Docker Compose enabled
- Git
- Python 3.x — only required for testing or running peers outside Docker

### Run the Demo

The easiest way to start the complete simulation is with the included demo launcher.

#### Windows

```powershell
.\launchers\demo.ps1
```

The launcher builds and starts the Docker stack, waits for the services to become ready, starts a Cloudflare Quick Tunnel, and displays the public demo URL in a separate terminal.

The network starts **empty**: open the URL, join with any node name and a room ID of your choosing, and let others join the same room. To also start the scripted cast (Alice, Bob, Mallory and swarm peers in room `demo`), run `.\launchers\demo.ps1 -DemoPeers` (or `./launchers/demo.sh --demo-peers`).

The generated URL can be opened with **Ctrl+Click**.

#### Linux / macOS

```bash
chmod +x launchers/demo.sh
./launchers/demo.sh
```

The shell launcher starts the same stack (empty network; `--demo-peers` adds the scripted cast) and prints the temporary public Cloudflare URL in the terminal.

> The Cloudflare Quick Tunnel does not require a Cloudflare account, API token, or persistent tunnel configuration.

### Run Locally

For local development without a public URL:

```bash
cp .env.example .env
docker compose up -d
```

Open the dashboard at:

**http://localhost:8080/**

Enter a node name and a room ID and press *Start PoS Peer*: the peer manager starts a real peer for you. The
first node in a room creates the network, and everyone who joins the same room ID discovers it through the
signalling server. Tick *Join as a malicious node* to add an attacker. For the scripted demo cast (Alice, Bob,
Mallory and swarm peers in room `demo`) start the stack with `docker compose --profile demo up -d`.

The public tunnel is not required for local access.

To stop and remove the running containers:

```bash
docker compose down
```

See [Docker Setup](docs/DOCKER.md) for more details.

### Services

| Service | Port | Purpose |
|---|---:|---|
| `frontend` | `8080` | Web dashboard |
| `signalling` | `7000` | Peer discovery |
| `peer-manager` | — (`7001`/`7002` inside the network) | Starts and stops the peers created from the browser |
| `cloudflared` | — | Public tunnel for the demo |
| `peer-alice`, `peer-bob` | `6001` / `6011` (API), `6002` / `6012` (events) | Honest peers (demo profile) |
| `peer-mallory` | — | Malicious peer (demo profile) |
| `peer-swarm` | — | Additional non-staking peers (demo profile) |

> **Note:** The `peer-*` services are enabled through the `demo` Compose profile, which is activated by `-DemoPeers` / `--demo-peers` on the launchers (or `docker compose --profile demo up -d`). By default the stack starts empty and peers come from the browser.

---

## Architecture

The system is composed of a web dashboard, REST API, signalling service, and a network of blockchain peers.

<img width="1536" height="1024" alt="Diagram" src="https://github.com/user-attachments/assets/b2b14ccc-bf17-410b-98a7-c34e35a1b3ba" />



The signalling service is used for **peer discovery**, not for exchanging blockchain data.

Once peers discover one another, blockchain communication takes place directly between peers.

The web API and dashboard provide an external view of the running simulation.

---

## Consensus

The simulation currently provides three consensus mechanisms:

| Mode | Directory | Behaviour |
|---|---|---|
| **Proof of Work** | `consensus/pow/` | Nodes compete to produce blocks |
| **Proof of Authority** | `consensus/poa/` | Approved validators produce blocks |
| **Proof of Stake** | `consensus/pos/` | Validators are selected according to stake |

Each consensus implementation includes its own peer-to-peer logic and malicious-node scenarios, allowing different attack and failure behaviours to be explored within the simulation.

The web API, the dashboard and the peer manager work with **Proof of Stake** (the mode this project focuses on).

### Proof-of-Stake fixes

The starter code shipped with bugs in its PoS consensus. These are fixed and covered by tests in `tests/`:

| Problem | Fix |
|---|---|
| Every node ran its own random lottery, so zero or several nodes could "win" an epoch and fork the chain | Deterministic, stake-weighted `elect_leader(seed, stakes)`: every node computes the same leader from shared data. Blocks from anyone else, or whose stake list omits or alters a known stake, are rejected |
| A double-signed block pair was never slashed (the chain-sync fork check was inverted; slashing checked a signature against the wrong block) | Same creator behind two different blocks at one height is slashed, both when chains are exchanged and immediately when the second block arrives |
| With several auto-stakers the chain forked: a stake received from a peer was stored without its signature, so the leader's block listed only its own stake and nodes disagreed about the staker set | Received stakes keep their signature, so every block carries the full signed stake list |
| After a double-sign, a node that had followed the other block stayed on its own branch and rejected every later block ("Hash Problem"), and the network never adopted its longer chain | After slashing, a node also follows the heavier chain, and asks its peers for chains immediately when it sees a block that does not build on its tip (instead of waiting for the 60 s periodic exchange) |
| Nodes that lost an election kept their stake locked forever | Stake state is cleared whenever an epoch ends |
| Empty blocks were rejected by receivers, so quiet epochs forked the network | A block may carry zero transactions; one is minted every epoch |
| Duplicate transactions slipped in (already in the previous block, or already in the mempool) | Duplicate checks on block validation and on receipt |
| Faucet/genesis mints crashed peer validation and could be forged | Signed with a faucet key, verified by every peer, capped at 500 |

Also under test: staking rules (non-stakers, non-positive or over-balance amounts and a second stake in one epoch
are rejected) and the genesis balance (exactly 50 coins, no miner reward).

To experiment with short epochs, set the `EPOCH_TIME` environment variable (seconds, default `60`) on every peer;
the staking window (5/6 of the epoch) and the minimum block spacing follow it.

### Malicious node and slashing

A node joined with the **malicious role** (`consensus/pos/malicious_peer.py`) double-signs whenever it is elected:
it sends two conflicting blocks to different halves of the network. Honest nodes detect the pair, mark the malicious block as invalid `is_valid: false` and flag its creator for slashing `slash_creator: true`. The malicious validator's stake is then slashed, and the affected block is displayed as **Slashed** in the dashboard.
Because the two blocks split the honest nodes onto different branches, a node that notices it is on the wrong one
requests chains from its peers straight away and switches to the heavier chain; the dashboard shows "Out of sync"
and then "Fork resolved" toasts.

---

## Project Structure

```text
Blockchain-Simulation/
├── README.md                         # Project overview and setup instructions
├── requirements.txt                  # Python runtime dependencies
├── requirements-dev.txt              # Development and test dependencies
├── docker-compose.yml                # Services and containers for running the project
├── start_peer.py                     # Starts a blockchain peer
├── peer_manager.py                   # Manages and coordinates peer processes
├── shared_blockchain_structures.py   # Blockchain data structures shared across modules
├── Dockerfile.peer                   # Docker image definition for a peer
├── Dockerfile.signalling             # Docker image definition for the signalling server
│
├── consensus/                        # Consensus protocols and peer implementations
│   ├── pow/                          # Proof-of-Work protocol
│   ├── pos/                          # Proof-of-Stake protocol (p2p.py, malicious_peer.py, ...)
│   └── poa/                          # Proof-of-Authority protocol
│
├── smart_contract/                   # Smart-contract execution and storage
│   ├── smart_contract.py             # Contract logic and interface
│   ├── secure_executor.py            # Executes contracts with security controls
│   ├── sandbox_runner.py             # Runs contract code in a sandbox
│   ├── gas_meter.py                  # Tracks contract execution cost
│   └── contracts_db.py               # Stores and retrieves contracts
│
├── storage/                          # Blockchain persistence utilities
│   └── storage_manager.py            # Reads and writes blockchain data
│
├── ipfs/                             # IPFS integration
│   └── ipfs.py                       # Stores and retrieves content through IPFS
│
├── signalling/                       # Peer discovery and connection signalling
│   ├── server.py                     # Signalling server
│   ├── client.py                     # Peer-side signalling client
│   └── healthcheck.py                # Signalling service health check
│
├── webapi/                           # HTTP API and real-time event endpoints
│   ├── server.py                     # Main web API server and routes
│   ├── events.py                     # Publishes blockchain events to clients
│   ├── rate_limit.py                 # API rate-limiting logic
│   └── healthcheck.py                # API service health check
│
├── web/                              # Web dashboard and frontend
│   ├── package.json                  # Frontend dependencies and scripts
│   ├── vite.config.ts                # Frontend build and development configuration
│   └── src/
│       ├── features/blockchain/      # Blockchain dashboard, connection flow, and tutorials
│       ├── components/               # Shared visual components
│       ├── routes/                   # Application pages and route definitions
│       ├── lib/                      # API client and shared frontend utilities
│       ├── server.ts                 # Frontend server entry point
│       └── styles.css                # Global frontend styles
│
├── tests/                            # Automated tests for blockchain and API behavior
├── docs/                             # API, Docker, and frontend documentation
└── launchers/                        # Demo launch scripts for supported platforms

```

---

## Development

### Backend

Install the project dependencies and run the test suite:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests/
```

The test suite covers the PoS fixes above (election, double-sign slashing, duplicate transactions, faucet mints, empty blocks, genesis balance), staking rules, auto-stake, peer management (roles, capacity, idle reaping, authorised stop), rate limiting, and spectator reports.

### Frontend

To work on the frontend independently:

```bash
cd web
npm install
npm run dev
```

The frontend uses TypeScript and Vite (dev server on port 8080). Its API calls need the peer manager and peers reachable, so for day-to-day work it is simpler to run the stack in Docker and rebuild after changes: `docker compose up -d --build frontend`. See [Frontend Guide](docs/FRONTEND_UX.md).

---

## Documentation

- [API Reference](docs/API.md): per-node REST and WebSocket API, peer manager API, roles, how the leader is chosen
- [Docker Setup](docs/DOCKER.md): services, the `demo` profile, joining from the browser, rebuilding
- [Frontend Guide](docs/FRONTEND_UX.md): views, features, demo script

---


