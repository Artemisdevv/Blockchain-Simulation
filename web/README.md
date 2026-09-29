# Frontend — Consensus Console

Vite + React + TypeScript + Tailwind + shadcn/ui.
Connected directly to live Docker container REST & Event WebSocket APIs.

## Run the whole thing (backend + frontend)

### 1. Backend (Docker)

From the repo root (`Blockchain-Simulation/`, not `web/`):

```bash
docker compose up -d --build
```

This starts the signalling server plus `alice`, `bob` (honest stakers) and `mallory` (malicious node).

### 2. Frontend

```bash
cd web
npm install
npm run dev
```

Opens on `http://localhost:5173`. On the connect screen:
- Click **"Connect to Peer Alice (:6001)"** or **"Connect to Peer Bob (:6011)"** for 1-click zero-friction login.
- Or click **"Spectator QR Code"** to share or open the direct spectator link (`http://localhost:5173/?node=alice`).
