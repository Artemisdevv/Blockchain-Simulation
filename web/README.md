# Frontend — Consensus Console

Vite + React + TypeScript (TanStack Start) + Tailwind + shadcn/ui. Currently
running on mock data (`src/features/blockchain/mock-data.ts` /
`mock-service.ts`) — real API wiring is the next step, see
`docs/FRONTEND_UX.md` and `docs/API.md` at the repo root.

## Run the whole thing (backend + frontend)

### 1. Backend (Docker)

From the repo root (`Blockchain-Simulation/`, not `web/`):

```
docker compose up -d --build
```

This starts the signalling server plus `alice`, `bob` (honest stakers) and
`mallory` (malicious node) — see `docs/DOCKER.md` for the full picture
(scaling to more nodes, driving mallory's malicious behavior live, etc).

**Get a peer's auth token** — every peer prints one at startup:

```
docker compose logs peer-alice
```

Look for a line like:

```
Auth token (also in .webapi_token_6000): <long-random-string>
```

That's the "Bearer token" the connect screen asks for. Copy the whole
string after the colon (no quotes, no trailing space). It's a fresh
per-process secret, not a personal login — see `docs/API.md` for why it
exists at all.

Alice's API is published on the host at `http://localhost:6001` (not
6000 — see `docker-compose.yml`'s port mapping), bob's at
`http://localhost:6011`.

### 2. Frontend

```
cd web
npm install
npm run dev
```

Opens on `http://localhost:5173` (or whatever Vite reports). On the connect
screen, enter:
- **Node API URL**: `http://localhost:6001` (alice) or `:6011` (bob)
- **Bearer token**: the string you copied above

### Not running Docker?

You can run a single peer directly instead (see repo root README for the
full interactive flow) — it prints the same kind of token line, just
without the `docker compose logs` step.

## What's mocked vs real right now

Everything on screen right now is `mock-data.ts` — connecting doesn't
actually hit the URL/token you enter yet. Wiring `mock-service.ts` to the
real endpoints in `docs/API.md` is the next milestone.
