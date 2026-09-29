"""Compose-local API for starting room peers and proxying their web APIs.

Peer processes stay inside this service container. They still use the normal
start_peer.py entry point, so signalling and P2P behavior remain shared with
the CLI and Compose demo peers.
"""
import asyncio
import atexit
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from flask import Flask, Response, jsonify, request
import websockets


BASE_PORT = int(os.environ.get("PEER_MANAGER_BASE_PORT", "5100"))
PORT_STEP = int(os.environ.get("PEER_MANAGER_PORT_STEP", "100"))
MAX_PEERS = int(os.environ.get("PEER_MANAGER_MAX_PEERS", "9"))
PEER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
ROOM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass
class ManagedPeer:
    peer_id: str
    name: str
    room_id: str
    port: int
    token: str
    process: subprocess.Popen


class PeerManager:
    def __init__(self, process_factory=subprocess.Popen, request_get=requests.get):
        self.process_factory = process_factory
        self.request_get = request_get
        self.peers: dict[str, ManagedPeer] = {}
        self._lock = threading.Lock()
        self._next_port = BASE_PORT

    def start_peer(self, name, room_id):
        name = str(name or "").strip()
        room_id = str(room_id or "").strip()
        if not PEER_NAME_RE.fullmatch(name):
            raise ValueError("Node name must be 1-32 letters, numbers, underscores, or hyphens.")
        if not ROOM_ID_RE.fullmatch(room_id):
            raise ValueError("Room ID must be 1-64 letters, numbers, underscores, or hyphens.")

        with self._lock:
            self._reap_exited()
            if len(self.peers) >= MAX_PEERS:
                raise RuntimeError("Peer manager is full. Restart the Compose stack to clear its temporary peers.")
            if any(peer.name.lower() == name.lower() for peer in self.peers.values()):
                raise ValueError(f"A managed peer named '{name}' is already running.")

            port = self._next_port
            self._next_port += PORT_STEP
            peer_id = uuid.uuid4().hex
            token = secrets.token_urlsafe(32)
            env = os.environ.copy()
            env.update({
                "PEER_HOST": os.environ.get("PEER_ADVERTISE_HOST", "peer-manager"),
                "PEER_PORT": str(port),
                "PEER_NAME": name,
                "CONSENSUS": "pos",
                "INTERACTIVE": "false",
                "DISK_LOAD": "n",
                "DISK_SAVE": "n",
                "ACTION": "room",
                "SIGNALLING_HOST": os.environ.get("SIGNALLING_HOST", "signalling"),
                "SIGNALLING_PORT": os.environ.get("SIGNALLING_PORT", "7000"),
                "ROOM_ID": room_id,
                "MALICIOUS": "n",
                "STAKER": "y",
                "WEBAPI_HOST": "0.0.0.0",
                "WEBAPI_TOKEN": token,
            })
            process = self.process_factory(
                [sys.executable, str(PROJECT_ROOT / "start_peer.py")],
                cwd=str(PROJECT_ROOT),
                env=env,
            )
            managed = ManagedPeer(peer_id, name, room_id, port, token, process)
            self.peers[peer_id] = managed

        if not self._wait_for_api(managed):
            self.stop_peer(peer_id)
            raise RuntimeError("PoS peer did not start its dashboard API. Check the peer-manager logs.")

        return managed

    def _wait_for_api(self, peer, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if peer.process.poll() is not None:
                return False
            try:
                response = self.request_get(
                    f"http://127.0.0.1:{peer.port + 1000}/balance",
                    headers={"Authorization": f"Bearer {peer.token}"},
                    timeout=0.5,
                )
                if response.ok:
                    return True
            except requests.RequestException:
                pass
            time.sleep(0.1)
        return False

    def _reap_exited(self):
        for peer_id, peer in list(self.peers.items()):
            if peer.process.poll() is not None:
                self.peers.pop(peer_id, None)

    def get_peer(self, peer_id):
        with self._lock:
            peer = self.peers.get(peer_id)
            if peer and peer.process.poll() is not None:
                self.peers.pop(peer_id, None)
                return None
            return peer

    def stop_peer(self, peer_id):
        with self._lock:
            peer = self.peers.pop(peer_id, None)
        if peer and peer.process.poll() is None:
            peer.process.terminate()
            try:
                peer.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                peer.process.kill()

    def stop_all(self):
        with self._lock:
            peer_ids = list(self.peers)
        for peer_id in peer_ids:
            self.stop_peer(peer_id)


def create_app(manager=None):
    manager = manager or PeerManager()
    app = Flask(__name__)

    @app.post("/peers")
    def create_peer():
        data = request.get_json(silent=True) or {}
        try:
            peer = manager.start_peer(data.get("name"), data.get("room_id"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503
        return jsonify({
            "peer_id": peer.peer_id,
            "name": peer.name,
            "room_id": peer.room_id,
            "token": peer.token,
        }), 201

    @app.route("/api/runtime/<peer_id>", defaults={"path": ""}, methods=["GET", "POST", "OPTIONS"])
    @app.route("/api/runtime/<peer_id>/<path:path>", methods=["GET", "POST", "OPTIONS"])
    def proxy_api(peer_id, path):
        peer = manager.get_peer(peer_id)
        if not peer:
            return jsonify({"error": "Peer is no longer running."}), 404
        upstream_url = f"http://127.0.0.1:{peer.port + 1000}/{path}"
        headers = {}
        for header in ("Authorization", "Content-Type"):
            if request.headers.get(header):
                headers[header] = request.headers[header]
        try:
            upstream = requests.request(
                request.method,
                upstream_url,
                params=request.args,
                data=request.get_data(),
                headers=headers,
                timeout=30,
            )
        except requests.RequestException:
            return jsonify({"error": "Peer API is not reachable."}), 502
        response_headers = {}
        if upstream.headers.get("Content-Type"):
            response_headers["Content-Type"] = upstream.headers["Content-Type"]
        return Response(upstream.content, status=upstream.status_code, headers=response_headers)

    return app, manager


async def run_ws_proxy(manager, websocket):
    path = urlparse(websocket.request.path).path.split("/")
    if len(path) != 5 or path[:3] != ["", "ws", "runtime"] or path[4] != "events":
        await websocket.close(code=4404, reason="unknown peer websocket")
        return
    peer = manager.get_peer(path[3])
    if not peer:
        await websocket.close(code=4404, reason="peer websocket unavailable")
        return

    query = urlparse(websocket.request.path).query
    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{peer.port + 1001}/events?{query}"
        ) as upstream:
            async def relay(source, target):
                async for message in source:
                    await target.send(message)

            tasks = [
                asyncio.create_task(relay(websocket, upstream)),
                asyncio.create_task(relay(upstream, websocket)),
            ]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except (OSError, websockets.exceptions.WebSocketException):
        await websocket.close(code=1011, reason="peer websocket is not reachable")


async def main():
    app, manager = create_app()
    atexit.register(manager.stop_all)
    http_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=7001, threaded=True, use_reloader=False),
        daemon=True,
    )
    http_thread.start()
    async with websockets.serve(lambda websocket: run_ws_proxy(manager, websocket), "0.0.0.0", 7002):
        print("Peer manager HTTP listening on :7001; events proxy listening on :7002", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
