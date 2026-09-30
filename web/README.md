# Frontend - Consensus Console

Vite + React + TypeScript + Tailwind + shadcn/ui (TanStack Start). It is one node's live view of a
Proof-of-Stake network; the browser starts a node through the peer manager and talks to it over REST and a
WebSocket.

Features, views, demo script and dev notes are in [`../docs/FRONTEND_UX.md`](../docs/FRONTEND_UX.md); the API it
consumes is in [`../docs/API.md`](../docs/API.md).

## Run everything

From the repo root (`Blockchain-Simulation/`, not `web/`):

```bash
docker compose up -d --build
```

Open **http://localhost:8080**, enter a node name and a room ID, and press *Start PoS Peer*.
For the scripted demo cast (alice, bob, mallory, swarm) add `--profile demo`; see [`../docs/DOCKER.md`](../docs/DOCKER.md).

## Frontend only

```bash
cd web
npm install
npm run dev     # http://localhost:8080
```

The dev server proxies the API to `localhost` ports (peer manager 7001/7002, alice 6001/6002, bob 6011/6012)
that Compose does not publish by default, so for day-to-day work rebuild the container instead:

```bash
docker compose up -d --build frontend
```
