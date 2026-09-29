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

The launcher builds and starts the Docker demo stack, waits for the services to become ready, starts a Cloudflare Quick Tunnel, and displays the public demo URL in a separate terminal.

The generated URL can be opened with **Ctrl+Click**.

#### Linux / macOS

```bash
chmod +x launchers/demo.sh
./launchers/demo.sh
```

The shell launcher starts the same demo stack and prints the temporary public Cloudflare URL in the terminal.

> The Cloudflare Quick Tunnel does not require a Cloudflare account, API token, or persistent tunnel configuration.

### Run Locally

For local development without a public URL:

```bash
cp .env.example .env
docker compose up -d
```

Open the dashboard at:

**http://localhost:8080/**

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
| `peer-alice`, `peer-bob` | `6000` inside network | Honest peers |
| `peer-mallory` | — | Malicious peer |
| `peer-swarm` | — | Additional peers |
| `peer-manager` | — | Peer lifecycle management |
| `cloudflared` | — | Public tunnel for the demo |

> **Note:** The `peer-*` services are enabled through the `demo` Compose profile, which is activated by the included demo launchers.

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

---

## Repository Layout

```text
consensus/        PoW, PoA and PoS implementations
signalling/       Signalling server, client and healthcheck
webapi/            Flask API, events and rate limiting
smart_contract/   Contract storage, gas metering and sandbox
storage/          Persistent storage manager
ipfs/              IPFS integration
web/              TypeScript / Vite frontend
tests/             Automated test suite
docs/              API, Docker and frontend documentation
launchers/         One-command demo launchers

peer_manager.py   Peer lifecycle management
start_peer.py     Peer entry point
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

The test suite covers consensus behaviour, staking, elections, genesis balances, empty blocks, peer management, rate limiting, spectator reports, and related functionality.

### Frontend

To work on the frontend independently:

```bash
cd web
npm install
npm run dev
```

The frontend uses TypeScript and Vite.

---

## Documentation

- [API Reference](docs/API.md)
- [Docker Setup](docs/DOCKER.md)
- [Frontend UX Notes](docs/FRONTEND_UX.md)

---
