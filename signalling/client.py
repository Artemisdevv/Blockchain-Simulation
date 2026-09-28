"""
Client-side helper for joining a room via the signalling server.
Consensus-agnostic - works with any Peer type (poa/pos/pow) since it only
returns plain (host, port, name, public_key) dicts; the caller decides what
to do with them (typically: bootstrap off the first one, or become genesis
if the room was empty).
"""
import asyncio
import json
import websockets


async def join_room(sig_host, sig_port, room_id, my_host, my_port, my_name, my_public_key,
                     on_peer_joined=None):
    """
    Joins `room_id` on the signalling server and returns the list of peers
    already registered in that room (empty list if we're first to join).

    If `on_peer_joined` is given, stays connected in the background and
    calls it with a peer dict for every node that joins the room later -
    lets an already-running node proactively connect to late joiners.
    Returns (initial_peers, listener_task_or_None).
    """
    uri = f"ws://{sig_host}:{sig_port}"
    websocket = await websockets.connect(uri)

    await websocket.send(json.dumps({
        "type": "join",
        "room": room_id,
        "host": my_host,
        "port": my_port,
        "name": my_name,
        "public_key": my_public_key,
    }))

    first_msg = json.loads(await websocket.recv())
    initial_peers = first_msg.get("peers", []) if first_msg.get("type") == "room_peers" else []

    listener_task = None
    if on_peer_joined:
        listener_task = asyncio.create_task(_listen(websocket, on_peer_joined))
    else:
        await websocket.close()

    return initial_peers, listener_task


async def _listen(websocket, on_peer_joined):
    try:
        async for raw in websocket:
            msg = json.loads(raw)
            if msg.get("type") == "peer_joined":
                on_peer_joined(msg["peer"])
    except websockets.exceptions.ConnectionClosed:
        pass
