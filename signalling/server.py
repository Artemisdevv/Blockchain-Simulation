"""
Signalling server for room-based peer discovery.

Nodes join a room by id. The server hands back the list of peers already
in that room; the joining node then bootstraps its P2P connection off one
of them using the existing handshake protocol (ping/pong/peer_info) - this
server only solves discovery, not the actual chain sync.

Run standalone: python -m signalling.server [port]
"""
import asyncio
import json
import sys
import websockets

# room_id -> {(host, port): (name, public_key)}
ROOMS = {}
# room_id -> {(host, port): websocket}
ROOM_SOCKETS = {}


async def handle(websocket):
    room_id = None
    endpoint = None
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "join":
                continue

            room_id = msg.get("room")
            host = msg.get("host")
            port = msg.get("port")
            name = msg.get("name")
            public_key = msg.get("public_key")

            if not all([room_id, host, port, name, public_key]):
                continue

            endpoint = (host, port)
            room = ROOMS.setdefault(room_id, {})
            sockets = ROOM_SOCKETS.setdefault(room_id, {})

            existing_peers = [
                {"host": h, "port": p, "name": n, "public_key": pk}
                for (h, p), (n, pk) in room.items()
            ]

            room[endpoint] = (name, public_key)
            sockets[endpoint] = websocket

            await websocket.send(json.dumps({
                "type": "room_peers",
                "room": room_id,
                "peers": existing_peers,
            }))

            announce = json.dumps({
                "type": "peer_joined",
                "room": room_id,
                "peer": {"host": host, "port": port, "name": name, "public_key": public_key},
            })
            for ep, ws in list(sockets.items()):
                if ep != endpoint:
                    try:
                        await ws.send(announce)
                    except Exception:
                        pass

            print(f"[signalling] '{name}' joined room '{room_id}' ({len(room)} peer(s) total)", flush=True)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if room_id and endpoint:
            room = ROOMS.get(room_id, {})
            sockets = ROOM_SOCKETS.get(room_id, {})
            room.pop(endpoint, None)
            sockets.pop(endpoint, None)

            leave_msg = json.dumps({
                "type": "peer_left",
                "room": room_id,
                "peer": {"host": endpoint[0], "port": endpoint[1]},
            })
            for ws in list(sockets.values()):
                try:
                    await ws.send(leave_msg)
                except Exception:
                    pass

            if not room:
                ROOMS.pop(room_id, None)
                ROOM_SOCKETS.pop(room_id, None)


async def main(host="0.0.0.0", port=7000):
    async with websockets.serve(handle, host, port):
        print(f"Signalling server listening on {host}:{port}", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7000
    asyncio.run(main(port=port))
