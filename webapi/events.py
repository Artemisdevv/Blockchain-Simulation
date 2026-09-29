"""
/events push feed - see docs/API.md.

Runs as a plain websockets server (same library the P2P layer already uses)
in the *same* asyncio event loop as the Peer, so no cross-thread bridging is
needed here (unlike webapi/server.py's Flask REST API, which runs in its own
thread). Peer code calls `peer.emit_event(...)` at a few points (new block,
new peer, new stake, slash) to push updates to connected browser clients.

Runs on a separate port from the REST API (REST_port + 1) since Flask's dev
server doesn't speak websocket without extra dependencies we don't have.

Auth: browsers can't set custom headers on a WebSocket handshake, so the
token is passed as a query param: ws://host:port/events?token=...
"""
import asyncio
import secrets
from urllib.parse import urlparse, parse_qs

import websockets

from webapi.rate_limit import RateLimiter, FailedAuthTracker

MAX_CONNECTIONS_PER_MINUTE = 30


def run_events_server(peer, host, port, token, limiter: RateLimiter = None, auth_tracker: FailedAuthTracker = None):
    """
    Schedules the events websocket server as a background task on the
    currently running event loop. Call this from inside the peer's loop
    (e.g. alongside run_api_server in start_peer.py's run_peer()).

    Pass the same `limiter`/`auth_tracker` instances used by run_api_server
    so a source blocked on the REST API is blocked here too.
    """
    limiter = limiter or RateLimiter(MAX_CONNECTIONS_PER_MINUTE, 60)
    auth_tracker = auth_tracker or FailedAuthTracker()

    async def handler(websocket):
        client = websocket.remote_address[0] if websocket.remote_address else "unknown"

        if auth_tracker.is_blocked(client):
            await websocket.close(code=4429, reason="too many failed auth attempts, try again later")
            return

        if not limiter.allow(client):
            await websocket.close(code=4429, reason="rate limit exceeded")
            return

        query = parse_qs(urlparse(websocket.request.path).query)
        provided = (query.get("token") or [None])[0]
        if not provided or not secrets.compare_digest(provided, token):
            auth_tracker.record_failure(client)
            await websocket.close(code=4401, reason="missing or invalid token")
            return
        auth_tracker.record_success(client)

        peer.event_subscribers.add(websocket)
        try:
            async for _ in websocket:
                pass  # no client->server messages expected, just keep the connection open
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            peer.event_subscribers.discard(websocket)

    async def serve_forever():
        async with websockets.serve(handler, host, port):
            print(f"Events websocket listening on ws://{host}:{port}/events (token required as ?token=...)\n")
            await asyncio.Future()

    return asyncio.create_task(serve_forever())
