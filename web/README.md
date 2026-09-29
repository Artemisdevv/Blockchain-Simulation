# Frontend

Vite + React + TypeScript + Tailwind v4 + [shadcn/ui](https://ui.shadcn.com).
Talks to a running peer's web API (`docs/API.md` at repo root) - REST polling
as a fallback, live updates via the `/events` websocket.

## Run

```
npm install
npm run dev
```

Start a PoS peer first (see repo root README), grab the token it prints,
and paste both into the connect screen.

## What's here (scaffold, not final)

- `src/lib/` - API client, types mirroring `docs/API.md`, connection storage
  (localStorage - not a login, see the comment in `connection.ts`)
- `src/hooks/useNetworkState.ts` - combines initial REST fetch with live
  `/events` updates; `src/hooks/useEvents.ts` - the websocket with
  reconnect-with-backoff
- `src/components/` - `ChainExplorer` (connected block cards),
  `StakersLeaderboard` (win-probability bars), `PeersList`, `ActionsCard`
  (send/stake forms), `SlashAlert` (the malicious-node-caught banner),
  `TopBar` (live status + epoch countdown)

## Design direction

Fintech-clean: light canvas, one indigo accent reserved for primary
actions/focus, green for live/confirmed, amber for pending, red
(shadcn's `destructive`) reserved strictly for the slash/malicious alert.
Monospace for hashes/keys/amounts, sans for everything else - see
`src/index.css` for the token values (`--primary`, `--success`,
`--warning`, `--live`, `--font-mono`).

## Not built yet (see docs/FRONTEND_UX.md for the full Tier 1/2 list)

- Peer topology graph (currently a plain list - `PeersList.tsx`)
- Transaction flow / block-arrival micro-animations
- Room-join screen (joining a network by room ID from the UI, not just
  connecting to an already-running peer's API)

## Adding shadcn components

```
npx shadcn@latest add <component>
```
