"""Compose-local API for starting room peers and proxying their web APIs.

Peer processes stay inside this service container. They still use the normal
start_peer.py entry point, so signalling and P2P behavior remain shared with
the CLI and Compose demo peers.
"""
import asyncio
import atexit
import base64
import hashlib
import hmac
import io
import json
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
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, TableStyle

import requests
from flask import Flask, Response, jsonify, request
import websockets


BASE_PORT = int(os.environ.get("PEER_MANAGER_BASE_PORT", "5100"))
PORT_STEP = int(os.environ.get("PEER_MANAGER_PORT_STEP", "100"))
MAX_PEERS = int(os.environ.get("PEER_MANAGER_MAX_PEERS", "9"))
# Peers whose dashboard has not touched the API for this long are stopped.
IDLE_TIMEOUT = float(os.environ.get("PEER_MANAGER_IDLE_TIMEOUT", "120"))
ROLES = ("honest", "malicious")
PEER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
ROOM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.environ.get("RUN_REPORT_DIR", PROJECT_ROOT / "runtime_reports"))
READ_ONLY_PATHS = {"chain", "peers", "mempool", "stakers", "metrics", "invariants", "attack-lab/state"}


def b64url(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_b64url(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_or_create_secret(filename):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


class RunContext:
    def __init__(self, room_id):
        self.run_id = uuid.uuid4().hex
        self.room_id = room_id
        self.started_at = time.time()
        self.ended_at = None
        self.participants = {}
        self.events = []
        self.final_state = {}

    @classmethod
    def from_report(cls, report):
        run = cls(report["run"]["room_id"])
        run.run_id = report["run"]["run_id"]
        run.started_at = report["run"]["started_at"]
        run.ended_at = report["run"].get("ended_at")
        run.participants = {p.get("peer_id") or p.get("public_key") or p.get("name"): p for p in report.get("participants", [])}
        run.events = report.get("events", [])
        run.final_state = report.get("final_state", {})
        return run

    def record(self, event, source=None):
        now = time.time()
        item = {"sequence": len(self.events) + 1, "timestamp": now, "type": event.get("type", "unknown"),
                "source_peer": source, "data": event}
        self.events.append(item)
        data = event.get("peer") or {}
        key = data.get("public_key") or data.get("name")
        if key:
            participant = self.participants.setdefault(key, {"public_key": data.get("public_key"), "name": data.get("name"), "first_seen_at": now})
            participant["last_seen_at"] = now

    def snapshot(self, peer, state):
        now = time.time()
        self.final_state = {"captured_at": now, "source_peer": peer.name, "chain": state.get("chain"),
                            "peers": state.get("peers"), "mempool": state.get("mempool"),
                            "stakers": state.get("stakers"), "metrics": state.get("metrics"),
                            "invariants": state.get("invariants"), "attack_lab_state": state.get("attack-lab/state"),
                            "completeness": {"chain": "current source peer snapshot", "peers": "currently reachable known peers", "mempool": "observed snapshot only", "attack_history": "events observed by gateway only", "participants": "first/last observation; not a complete signalling history"}}

    def observe_peers(self, peers, source=None):
        now = time.time()
        observed = {p.get("public_key"): p for p in peers if p.get("public_key")}
        for key, peer in observed.items():
            participant = self.participants.get(key)
            if participant is None:
                participant = next((item for item in self.participants.values() if item.get("name") == peer.get("name") and not item.get("public_key")), None)
                if participant:
                    old_key = next(old_key for old_key, item in self.participants.items() if item is participant)
                    self.participants.pop(old_key, None)
                    participant["public_key"] = key
                    self.participants[key] = participant
            if participant is None:
                self.participants[key] = {"public_key": key, "name": peer.get("name"), "first_seen_at": now, "last_seen_at": now}
                self.record({"type": "participant_joined", "peer": peer}, source)
            else:
                participant["name"] = peer.get("name") or participant.get("name")
                participant["last_seen_at"] = now
                if participant.pop("status", None) == "not_observed":
                    self.record({"type": "participant_reobserved", "peer": peer}, source)
        for key, participant in list(self.participants.items()):
            if participant.get("public_key") and key not in observed and participant.get("status") != "not_observed":
                participant["status"] = "not_observed"
                participant["last_seen_at"] = now
                self.record({"type": "participant_left_or_not_observed", "peer": participant}, source)

    def report(self):
        return {"schema_version": 1, "run": {"run_id": self.run_id, "room_id": self.room_id,
                "started_at": self.started_at, "ended_at": self.ended_at, "duration_seconds": round((self.ended_at or time.time()) - self.started_at, 1)},
                "participants": list(self.participants.values()), "events": self.events, "final_state": self.final_state}

    def persist_event(self, item):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with (REPORT_DIR / f"{self.run_id}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, default=str) + "\n")
        (REPORT_DIR / f"{self.run_id}.json").write_text(json.dumps(self.report(), indent=2, default=str), encoding="utf-8")

    def persist(self):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / f"{self.run_id}.json").write_text(json.dumps(self.report(), indent=2, default=str), encoding="utf-8")


@dataclass
class ManagedPeer:
    peer_id: str
    name: str
    room_id: str
    port: int
    token: str
    process: subprocess.Popen
    last_seen: float = 0.0
    role: str = "honest"


class PeerManager:
    def __init__(self, process_factory=subprocess.Popen, request_get=requests.get):
        self.process_factory = process_factory
        self.request_get = request_get
        self.peers: dict[str, ManagedPeer] = {}
        self._lock = threading.Lock()
        self._next_port = BASE_PORT
        self._free_ports: list[int] = []
        self.runs = {}
        self.event_loop = None
        self.collector_futures = []
        self.signing_key = os.environ.get("SPECTATOR_SIGNING_KEY") or load_or_create_secret(".spectator_signing_key")
        self.issuer_token = os.environ.get("SPECTATOR_ISSUER_TOKEN") or load_or_create_secret(".spectator_issuer_token")
        try:
            self.fixed_peers = json.loads(os.environ.get("PEER_MANAGER_ROOM_PEERS", "[]"))
        except json.JSONDecodeError:
            self.fixed_peers = []
        self._load_runs()

    def _load_runs(self):
        if not REPORT_DIR.exists():
            return
        for report_path in REPORT_DIR.glob("*.json"):
            try:
                run = RunContext.from_report(json.loads(report_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            current = self.runs.get(run.room_id)
            if current is None or run.started_at > current.started_at:
                self.runs[run.room_id] = run

    def start_peer(self, name, room_id, role="honest"):
        role = str(role or "honest").strip().lower()
        if role not in ROLES:
            raise ValueError("Role must be 'honest' or 'malicious'.")
        malicious = role == "malicious"
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

            if self._free_ports:
                port = self._free_ports.pop(0)
            else:
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
                "MALICIOUS": "y" if malicious else "n",
                "STAKER": "y",
                # Honest nodes start with auto-stake off (several auto-stakers can still
                # fall a block behind; flip it from the dashboard toggle). A malicious
                # node stakes automatically, otherwise it never gets to attack.
                "AUTO_STAKE": "true" if malicious else "false",
                "PYTHONUNBUFFERED": "1",
                "WEBAPI_HOST": "0.0.0.0",
                "WEBAPI_TOKEN": token,
            })
            process = self.process_factory(
                [sys.executable, str(PROJECT_ROOT / "start_peer.py")],
                cwd=str(PROJECT_ROOT),
                env=env,
            )
            managed = ManagedPeer(peer_id, name, room_id, port, token, process, time.monotonic(), role)
            self.peers[peer_id] = managed
            run = self.begin_run(room_id)
            run.participants[peer_id] = {"peer_id": peer_id, "name": name, "first_seen_at": time.time(), "last_seen_at": time.time()}
            run.persist()

        if not self._wait_for_api(managed):
            self.stop_peer(peer_id)
            raise RuntimeError("PoS peer did not start its dashboard API. Check the peer-manager logs.")

        self.start_collector(room_id, {"name": name, "base_url": f"http://127.0.0.1:{port + 1000}", "token": token})

        return managed

    def start_collector(self, room_id, candidate):
        if self.event_loop and self.event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._collect_events(room_id, candidate), self.event_loop)
            self.collector_futures.append(future)

    async def _collect_events(self, room_id, candidate):
        parsed = urlparse(candidate["base_url"])
        ws_url = f"ws://{parsed.hostname}:{parsed.port + 1}/events?token={candidate['token']}"
        while True:
            try:
                async with websockets.connect(ws_url) as upstream:
                    async for message in upstream:
                        try:
                            self.record_event(room_id, json.loads(message), candidate["name"])
                        except (ValueError, TypeError):
                            continue
            except (OSError, websockets.exceptions.WebSocketException):
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(2)

    async def monitor_rooms(self):
        while True:
            room_ids = {p.get("room_id") for p in self.fixed_peers}
            with self._lock:
                room_ids.update(self.runs)
                room_ids.update(p.room_id for p in self.peers.values() if p.process.poll() is None)
            for room_id in filter(None, room_ids):
                reachable = False
                for candidate in self.room_peers(room_id):
                    try:
                        response = await asyncio.to_thread(requests.get, f"{candidate['base_url']}/peers", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=4)
                        if response.ok:
                            run = self.begin_run(room_id)
                            run.observe_peers(response.json().get("peers", []), candidate["name"])
                            run.ended_at = None
                            run.persist()
                            reachable = True
                            break
                    except (requests.RequestException, ValueError):
                        continue
                if not reachable and room_id in self.runs:
                    run = self.runs[room_id]
                    run.ended_at = run.ended_at or time.time()
                    run.persist()
            await asyncio.sleep(10)

    def token_in_room(self, token, room_id):
        with self._lock:
            return any(
                peer.room_id == room_id and peer.process.poll() is None
                and secrets.compare_digest(peer.token, token)
                for peer in self.peers.values()
            )

    def room_peers(self, room_id):
        with self._lock:
            managed = [peer for peer in self.peers.values() if peer.room_id == room_id and peer.process.poll() is None]
        candidates = [{"name": p.name, "room_id": p.room_id, "base_url": f"http://127.0.0.1:{p.port + 1000}", "token": p.token} for p in managed]
        for configured in self.fixed_peers:
            if configured.get("room_id") == room_id:
                candidates.append(configured)
        return candidates

    def find_token_owner(self, token):
        with self._lock:
            for peer in self.peers.values():
                if secrets.compare_digest(peer.token, token) and peer.process.poll() is None:
                    return peer.room_id
        for candidate in self.fixed_peers:
            if secrets.compare_digest(str(candidate.get("token", "")), token):
                return candidate.get("room_id")
        return None

    def make_spectator_token(self, room_id):
        payload = b64url(json.dumps({"room_id": room_id, "expires": int(time.time()) + 86400}, separators=(",", ":")).encode())
        signing_key = hashlib.sha256(f"{self.signing_key}:{self.issuer_token}".encode()).digest()
        signature = hmac.new(signing_key, payload.encode(), hashlib.sha256).digest()
        return f"{payload}.{b64url(signature)}"

    def verify_spectator_token(self, token):
        try:
            payload, signature = token.split(".", 1)
            signing_key = hashlib.sha256(f"{self.signing_key}:{self.issuer_token}".encode()).digest()
            expected = hmac.new(signing_key, payload.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(expected, decode_b64url(signature)):
                return None
            decoded = json.loads(decode_b64url(payload))
            if decoded["expires"] < time.time():
                return None
            return decoded["room_id"]
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def record_event(self, room_id, event, source=None):
        run = self.runs.get(room_id)
        if run is None:
            run = self.runs[room_id] = RunContext(room_id)
        run.record(event, source)
        run.persist_event(run.events[-1])

    def get_run(self, room_id):
        run = self.runs.get(room_id)
        if run is None:
            run = self.runs[room_id] = RunContext(room_id)
        return run

    def begin_run(self, room_id):
        run = self.runs.get(room_id)
        if run is None or run.ended_at:
            run = self.runs[room_id] = RunContext(room_id)
        return run

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

    def _release(self, peer):
        self.peers.pop(peer.peer_id, None)
        if peer.port not in self._free_ports:
            self._free_ports.append(peer.port)

    def _reap_exited(self):
        now = time.monotonic()
        for peer in list(self.peers.values()):
            if peer.process.poll() is not None:
                self._release(peer)
                run = self.runs.get(peer.room_id)
                participant = run.participants.get(peer.peer_id) if run else None
                if participant:
                    participant["last_seen_at"] = time.time()
                    run.persist()
            elif now - peer.last_seen > IDLE_TIMEOUT:
                # Dashboard went away without disconnecting (tab closed, crash).
                self._release(peer)
                self._terminate(peer)

    @staticmethod
    def _terminate(peer):
        if peer.process.poll() is None:
            peer.process.terminate()
            try:
                peer.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                peer.process.kill()

    def get_peer(self, peer_id):
        with self._lock:
            peer = self.peers.get(peer_id)
            if peer and peer.process.poll() is not None:
                self._release(peer)
                return None
            if peer:
                peer.last_seen = time.monotonic()
            return peer

    def stop_peer(self, peer_id):
        with self._lock:
            peer = self.peers.get(peer_id)
            if peer:
                self._release(peer)
        if peer:
            self._terminate(peer)
        return peer

    def stop_all(self):
        with self._lock:
            peer_ids = list(self.peers)
        for peer_id in peer_ids:
            self.stop_peer(peer_id)


def _json_body():
    """The request's JSON object, or {} for a missing / invalid / non-object body (list, number...)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def create_app(manager=None):
    manager = manager or PeerManager()
    app = Flask(__name__)
    # Every legitimate request is tiny JSON; this stops an unauthenticated caller streaming
    # huge bodies into /peers, /spectator-links or through the /api/runtime proxy.
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.post("/peers")
    def create_peer():
        data = _json_body()
        try:
            peer = manager.start_peer(data.get("name"), data.get("room_id"), data.get("role", "honest"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503
        return jsonify({
            "peer_id": peer.peer_id,
            "name": peer.name,
            "room_id": peer.room_id,
            "role": peer.role,
            "token": peer.token,
        }), 201

    @app.delete("/peers/<peer_id>")
    def delete_peer(peer_id):
        target = manager.get_peer(peer_id)
        if not target:
            return jsonify({"error": "Peer is no longer running."}), 404
        # The caller must hold the token of a live peer in the target's room: a node
        # can disconnect itself, and the Attack Lab can stop a room-mate, but nobody
        # can kill peers in rooms they are not part of.
        auth = request.headers.get("Authorization", "")
        supplied = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        if not supplied or not manager.token_in_room(supplied, target.room_id):
            return jsonify({"error": "A token for a peer in this room is required."}), 403
        manager.stop_peer(peer_id)
        return jsonify({"stopped": peer_id}), 200

    @app.get("/peers")
    def list_peers():
        with manager._lock:
            manager._reap_exited()
            peers = [
                {"peer_id": peer.peer_id, "name": peer.name, "room_id": peer.room_id, "role": peer.role}
                for peer in manager.peers.values()
            ]
        return jsonify({"peers": peers})

    @app.post("/spectator-links")
    def create_spectator_link():
        # Only someone who holds a peer token for a room can share it: the room comes
        # from the token, not from the request body, so you can't mint links for
        # rooms you are not part of.
        auth = request.headers.get("Authorization", "")
        supplied = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        room_id = manager.find_token_owner(supplied) if supplied else None
        if not room_id:
            return jsonify({"error": "A peer token for this room is required to create a spectator link."}), 403
        if not manager.room_peers(room_id):
            return jsonify({"error": "No accessible peers are currently available for this room."}), 404
        return jsonify({"room_id": room_id, "spectator_token": manager.make_spectator_token(room_id)})

    @app.route("/spectator/<token>/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def spectator_api(token, path):
        if request.method == "OPTIONS":
            return "", 204
        room_id = manager.verify_spectator_token(token)
        supplied = request.headers.get("Authorization", "")
        if not room_id or supplied != f"Bearer {token}":
            return jsonify({"error": "Invalid or expired spectator credential."}), 401
        if request.method != "GET" or path not in READ_ONLY_PATHS:
            return jsonify({"error": "Spectator access is read-only."}), 403
        candidates = manager.room_peers(room_id)
        for candidate in candidates:
            try:
                upstream = requests.get(f"{candidate['base_url']}/{path}", headers={"Authorization": f"Bearer {candidate['token']}"}, params=request.args, timeout=5)
                if upstream.ok:
                    run = manager.get_run(room_id)
                    if path == "peers":
                        run.observe_peers(upstream.json().get("peers", []), candidate["name"])
                        run.persist()
                    return Response(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))
            except (requests.RequestException, ValueError):
                continue
        return jsonify({"error": "No peer API is currently reachable for this room."}), 503

    @app.route("/spectator/<token>/report.<format>", methods=["GET"])
    def spectator_report(token, format):
        room_id = manager.verify_spectator_token(token)
        if not room_id or request.headers.get("Authorization") != f"Bearer {token}":
            return jsonify({"error": "Invalid or expired spectator credential."}), 401
        if format not in ("json", "pdf"):
            return jsonify({"error": "Report format must be json or pdf."}), 404
        run = manager.get_run(room_id)
        candidates = manager.room_peers(room_id)
        state = {}
        source = None
        for candidate in candidates:
            for endpoint in READ_ONLY_PATHS:
                try:
                    response = requests.get(f"{candidate['base_url']}/{endpoint}", headers={"Authorization": f"Bearer {candidate['token']}"}, timeout=5)
                    if response.ok:
                        state[endpoint] = response.json()
                        source = candidate['name']
                except (requests.RequestException, ValueError):
                    pass
            if state:
                break
        if state:
            if run.ended_at:
                run = manager.begin_run(room_id)
            run.snapshot(type("SourcePeer", (), {"name": source})(), state)
            run.ended_at = None
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            (REPORT_DIR / f"{run.run_id}.json").write_text(json.dumps(run.report(), indent=2, default=str), encoding="utf-8")
        else:
            run.ended_at = run.ended_at or time.time()
            run.persist()
        report = run.report()
        if format == "json":
            return jsonify(report)
        output = io.BytesIO()
        build_report_pdf(report, output)
        return Response(output.getvalue(), content_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=run-{run.run_id}.pdf"})

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


def build_report_pdf(report, output):
    from xml.sax.saxutils import escape

    run = report.get("run", {})
    final_state = report.get("final_state", {})
    events = sorted(report.get("events", []), key=lambda item: (item.get("timestamp", 0), item.get("sequence", 0)))
    chain = (final_state.get("chain") or {}).get("blocks", [])
    valid_chain = [block for block in chain if block.get("is_valid", True)]
    final_mempool = (final_state.get("mempool") or {}).get("transactions", [])
    block_events = [event for event in events if event.get("type") == "block_appended"]
    observed_block_ids = {
        event.get("data", {}).get("block", {}).get("id")
        for event in block_events
        if event.get("data", {}).get("block", {}).get("id")
    }

    # Count and display a transaction once by its canonical ID. The block/API
    # entry count remains available in the metrics table with an explicit label.
    confirmed_by_id = {}
    missing_id_entries = []
    for block in valid_chain:
        for tx in block.get("transactions", []):
            tx_id = tx.get("id")
            if tx_id:
                confirmed_by_id.setdefault(str(tx_id), (block, tx))
            else:
                missing_id_entries.append((block, tx))

    def utc_time(value, unknown="Unavailable"):
        if not isinstance(value, (int, float)):
            return unknown
        if value > 100_000_000_000:  # block timestamps are milliseconds
            value /= 1000
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(value))

    def short_id(value, limit=24):
        value = str(value or "Unavailable").replace("\n", " ").strip()
        if "BEGIN PUBLIC KEY" in value:
            return f"key:{hashlib.sha256(value.encode()).hexdigest()[:12]}"
        if len(value) > limit:
            return value[:limit - 13] + "..." + value[-10:]
        return value

    def short_value(value):
        if isinstance(value, dict):
            return "; ".join(f"{key}: {short_value(item)}" for key, item in value.items()) or "—"
        if isinstance(value, (list, tuple, set)):
            return ", ".join(short_value(item) for item in value) or "—"
        if value is None or value == "":
            return "—"
        if isinstance(value, str) and "BEGIN PUBLIC KEY" in value:
            return short_id(value)
        text = str(value)
        return short_id(text, 46)

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#17324D")
    blue = colors.HexColor("#245B83")
    pale = colors.HexColor("#EAF1F6")
    rule = colors.HexColor("#D5DEE7")
    muted = colors.HexColor("#5F6F7D")
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=navy, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["BodyText"], fontSize=9, leading=12, textColor=muted, spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=navy, spaceBefore=10, spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=7.5, leading=9, splitLongWords=True, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CellSmall", parent=styles["Cell"], fontSize=6.5, leading=8))
    styles.add(ParagraphStyle(name="CellHeader", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=colors.white, fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name="MetricLabel", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=navy, fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="MetricValue", parent=styles["Cell"], fontName="Helvetica-Bold", textColor=blue, fontSize=13, leading=15, alignment=TA_LEFT))

    doc = SimpleDocTemplate(
        output,
        pagesize=letter,
        title=f"Blockchain Run Report - {run.get('run_id', 'unknown')}",
        author="Blockchain Simulation",
        rightMargin=38,
        leftMargin=38,
        topMargin=50,
        bottomMargin=42,
    )

    def para(value, style="Cell"):
        return Paragraph(escape(str(value if value is not None else "—")).replace("\n", "<br/>"), styles[style])

    def make_table(rows, widths, header=True, repeat=1, compact=False):
        table_rows = []
        for row_index, row in enumerate(rows):
            style = "CellHeader" if header and row_index == 0 else ("CellSmall" if compact else "Cell")
            table_rows.append([item if isinstance(item, Paragraph) else para(item, style) for item in row])
        table_class = LongTable if len(table_rows) > 12 else Table
        table = table_class(table_rows, colWidths=widths, repeatRows=repeat if header else 0, hAlign="LEFT")
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.35, rule),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), navy)]
        start = 1 if header else 0
        commands += [("ROWBACKGROUNDS", (0, start), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")])]
        table.setStyle(TableStyle(commands))
        return table

    def section(title, table_or_flowable):
        return [Paragraph(escape(title), styles["SectionTitle"]), table_or_flowable, Spacer(1, 6)]

    def page_chrome(canvas, document):
        canvas.saveState()
        width, height = letter
        canvas.setStrokeColor(rule)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, height - 34, width - doc.rightMargin, height - 34)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, height - 27, "BLOCKCHAIN SIMULATION  /  RUN REPORT")
        canvas.line(doc.leftMargin, 30, width - doc.rightMargin, 30)
        canvas.drawString(doc.leftMargin, 18, f"Room {short_id(run.get('room_id'), 32)}  |  Run {short_id(run.get('run_id'), 28)}")
        canvas.drawRightString(width - doc.rightMargin, 18, f"Page {document.page}")
        canvas.restoreState()

    story = [
        Paragraph("Blockchain Run Report", styles["ReportTitle"]),
        Paragraph("Judge-facing summary of the observed simulation run", styles["ReportSubtitle"]),
    ]

    metadata = [
        ["Room ID", run.get("room_id", "Unavailable"), "Run ID", run.get("run_id", "Unavailable")],
        ["Started (UTC)", utc_time(run.get("started_at")), "Ended (UTC)", utc_time(run.get("ended_at"), "Still active at export")],
        ["Duration", f"{run.get('duration_seconds', 'Unavailable')} seconds", "Snapshot (UTC)", utc_time(final_state.get("captured_at"))],
    ]
    meta_rows = [[para(item, "MetricLabel" if index % 2 == 0 else "Cell") for index, item in enumerate(row)] for row in metadata]
    meta_table = Table(meta_rows, colWidths=[75, 176, 82, 157], hAlign="LEFT")
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), pale), ("BACKGROUND", (2, 0), (2, -1), pale),
        ("GRID", (0, 0), (-1, -1), 0.4, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend(section("Run Details", meta_table))

    participants_by_id = {}
    for index, participant in enumerate(report.get("participants", [])):
        name = participant.get("name") or "Unknown"
        identity = participant.get("public_key") or participant.get("peer_id") or f"name:{name}"
        item = participants_by_id.get(identity)
        if item is None:
            item = {**participant, "name": name, "_identity": identity}
            participants_by_id[identity] = item
        else:
            first_values = [value for value in (item.get("first_seen_at"), participant.get("first_seen_at")) if isinstance(value, (int, float))]
            last_values = [value for value in (item.get("last_seen_at"), participant.get("last_seen_at")) if isinstance(value, (int, float))]
            if first_values:
                item["first_seen_at"] = min(first_values)
            if last_values:
                item["last_seen_at"] = max(last_values)
            if participant.get("status") != "not_observed":
                item["status"] = participant.get("status", "observed")
    participants = list(participants_by_id.values())

    stakers = (final_state.get("stakers") or {}).get("stakers", {}) or {}
    active_stakers = {key: value for key, value in stakers.items() if isinstance(value, (int, float)) and value > 0}
    summary_rows = [
        ["Result", "Value", "Result", "Value"],
        ["Final valid blocks", str(len(valid_chain)), "Confirmed transactions", str(len(confirmed_by_id))],
        ["Pending transactions", str(len(final_mempool)), "block_appended events observed", str(len(block_events))],
        ["Unique blocks observed", str(len(observed_block_ids)), "Participants", str(len(participants))],
        ["Active validators", str(len(active_stakers)), "Duration", f"{run.get('duration_seconds', '—')} sec"],
    ]
    summary_table = make_table(summary_rows, [160, 52, 160, 84])
    story.extend(section("Key Results", summary_table))
    story.append(para("Confirmed transactions are unique IDs in valid blocks. Pending transactions are mempool entries at the final snapshot. block_appended counts event records and may repeat a block ID across peers; unique blocks observed counts distinct IDs in those events.", "CellSmall"))
    story.append(Spacer(1, 4))

    participant_rows = [["Participant", "Public key / identity", "First observed (UTC)", "Last observed (UTC)", "Status"]]
    for participant in participants:
        participant_rows.append([
            participant.get("name") or "Unknown",
            short_id(participant.get("public_key") or participant.get("peer_id") or participant.get("_identity")),
            utc_time(participant.get("first_seen_at")),
            utc_time(participant.get("last_seen_at")),
            participant.get("status", "observed").replace("_", " "),
        ])
    if not participants:
        participant_rows.append(["No participants recorded", "—", "—", "—", "—"])
    story.extend(section("Participants", make_table(participant_rows, [76, 118, 112, 112, 98], compact=True)))

    # Keep observed append events distinct from the final chain snapshot.
    append_rows = [["Observed (UTC)", "Block time (UTC)", "Source peer", "Block ID", "Creator", "Stake", "Tx entries"]]
    for event in block_events:
        block = event.get("data", {}).get("block", {})
        append_rows.append([
            utc_time(event.get("timestamp")), utc_time(block.get("ts")),
            event.get("source_peer") or "Unknown", short_id(block.get("id")), short_id(block.get("creator")),
            str(block.get("staked_amt", 0)),
            str(len(block.get("transactions", []))),
        ])
    if not block_events:
        append_rows.append(["No block_appended events recorded", "—", "—", "—", "—", "—", "—"])
    story.extend(section("Block Append Event History", make_table(append_rows, [83, 83, 57, 91, 98, 48, 56], compact=True)))

    final_block_rows = [["Height", "Block ID", "Creator", "Timestamp (UTC)", "Stake", "Tx entries"]]
    for height, block in enumerate(valid_chain, start=1):
        final_block_rows.append([
            str(height), short_id(block.get("id")), short_id(block.get("creator")),
            utc_time(block.get("ts")), str(block.get("staked_amt", 0)),
            str(len(block.get("transactions", []))),
        ])
    if not valid_chain:
        final_block_rows.append(["—", "No valid blocks in snapshot", "—", "—", "—", "—"])
    story.extend(section("Final Valid Chain Blocks", make_table(final_block_rows, [40, 112, 102, 120, 58, 84], compact=True)))

    tx_rows = [["Transaction ID", "Sender", "Receiver", "Included block", "Payload"]]
    for tx_id, (block, tx) in confirmed_by_id.items():
        tx_rows.append([
            short_id(tx_id), short_id(tx.get("sender")), short_id(tx.get("receiver")),
            short_id(block.get("id")), short_value(tx.get("payload")),
        ])
    for block, tx in missing_id_entries:
        tx_rows.append(["Missing transaction ID", short_id(tx.get("sender")), short_id(tx.get("receiver")), short_id(block.get("id")), short_value(tx.get("payload"))])
    if len(tx_rows) == 1:
        tx_rows.append(["No confirmed transactions in valid blocks", "—", "—", "—", "—"])
    story.extend(section("Confirmed Transactions", make_table(tx_rows, [91, 108, 78, 103, 136], compact=True)))

    mempool_rows = [["Transaction ID", "Sender", "Receiver", "Payload"]]
    for tx in final_mempool:
        mempool_rows.append([short_id(tx.get("id")), short_id(tx.get("sender")), short_id(tx.get("receiver")), short_value(tx.get("payload"))])
    if not final_mempool:
        mempool_rows.append(["No pending transactions at snapshot", "—", "—", "—"])
    story.extend(section("Pending Transactions (Mempool Snapshot)", make_table(mempool_rows, [105, 125, 110, 176], compact=True)))

    stake_rows = [["Validator / staker", "Current stake"]]
    for identity, amount in active_stakers.items():
        stake_rows.append([short_id(identity), str(amount)])
    if not active_stakers:
        stake_rows.append(["No active validator stakes in snapshot", "—"])
    story.extend(section("Validators and Current Stakes", make_table(stake_rows, [370, 146])))

    attacks = [event for event in events if "attack" in str(event.get("type", "")) or event.get("type") == "node_slashed"]
    attack_rows = [["Time (UTC)", "Event", "Source", "Details"]]
    for event in attacks:
        payload = event.get("data", {}) or {}
        detail = {key: value for key, value in payload.items() if key not in ("type", "block")}
        if payload.get("block"):
            detail["block_id"] = payload["block"].get("id") if isinstance(payload["block"], dict) else payload["block"]
        attack_rows.append([utc_time(event.get("timestamp")), event.get("type", "unknown"), event.get("source_peer") or "Unknown", short_value(detail)])
    if not attacks:
        attack_rows.append(["No attack events observed", "—", "—", "—"])
    story.extend(section("Attack Lab Activity", make_table(attack_rows, [102, 95, 75, 244], compact=True)))

    state_rows = [["Area", "Snapshot value / status"]]
    state_rows.append(["Snapshot source", final_state.get("source_peer", "Unavailable")])
    state_rows.append(["Snapshot time (UTC)", utc_time(final_state.get("captured_at"))])
    state_rows.append(["Reachable peers", ", ".join(peer.get("name", "Unknown") for peer in ((final_state.get("peers") or {}).get("peers", []))) or "Unavailable"])
    metrics = final_state.get("metrics", {}) or {}
    metric_labels = {
        "total_transactions": "Peer API transaction entries (may include repeated IDs)",
        "blocks_count": "Peer API chain block entries",
        "mempool_count": "Peer API mempool entries",
        "peer_count": "Peer API reachable peer count",
        "total_staked": "Peer API total stake",
        "avg_block_time_sec": "Peer API average block time (sec)",
        "room_id": "Peer API room ID",
    }
    for key, value in metrics.items():
        state_rows.append([metric_labels.get(key, key.replace("_", " ").title()), short_value(value)])
    invariants = final_state.get("invariants", {}) or {}
    for key, value in invariants.items():
        if isinstance(value, bool):
            value = "PASS" if value else "CHECK"
        state_rows.append([f"Invariant: {key.replace('_', ' ')}", short_value(value)])
    attack_state = final_state.get("attack_lab_state", {}) or {}
    for key, value in attack_state.items():
        state_rows.append([f"Attack Lab: {key.replace('_', ' ')}", short_value(value)])
    for key, value in (final_state.get("completeness", {}) or {}).items():
        state_rows.append([f"Coverage: {key.replace('_', ' ')}", short_value(value)])
    story.extend(section("Final State and Data Coverage", make_table(state_rows, [168, 348], compact=True)))

    timeline_rows = [["#", "Time (UTC)", "Event", "Source", "Event details"]]
    for event in events:
        payload = event.get("data", {}) or {}
        if event.get("type") == "block_appended":
            block = payload.get("block", {}) or {}
            details = f"Block {short_id(block.get('id'))}; {len(block.get('transactions', []))} transaction entries"
        else:
            details = short_value({key: value for key, value in payload.items() if key != "type"})
        timeline_rows.append([
            str(event.get("sequence", "—")), utc_time(event.get("timestamp")),
            event.get("type", "unknown").replace("_", " "),
            event.get("source_peer") or "Unknown", details,
        ])
    if not events:
        timeline_rows.append(["—", "—", "No live events recorded", "—", "—"])
    story.extend(section("Event Timeline", make_table(timeline_rows, [28, 112, 100, 66, 210], compact=True)))

    if missing_id_entries:
        story.append(Spacer(1, 4))
        story.append(para(f"Data note: {len(missing_id_entries)} transaction entries in valid blocks have no ID. They are shown above, but excluded from the confirmed unique-ID total.", "CellSmall"))

    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)


async def run_ws_proxy(manager, websocket):
    path = urlparse(websocket.request.path).path.split("/")
    spectator = len(path) == 6 and path[:3] == ["", "ws", "runtime"] and path[3] == "spectator" and path[5] == "events"
    if spectator:
        room_id = manager.verify_spectator_token(path[4])
        if not room_id:
            await websocket.close(code=4401, reason="invalid spectator credential")
            return
        candidates = manager.room_peers(room_id)
        if not candidates:
            await websocket.close(code=4404, reason="room unavailable")
            return
        peer = candidates[0]
        upstream_url = f"ws://{peer['base_url'].split('://', 1)[1].rsplit(':', 1)[0]}:{int(peer['base_url'].rsplit(':', 1)[1]) + 1}/events?token={peer['token']}"
    else:
        if len(path) != 5 or path[:3] != ["", "ws", "runtime"] or path[4] != "events":
            await websocket.close(code=4404, reason="unknown peer websocket")
            return
        peer = manager.get_peer(path[3])
        if not peer:
            await websocket.close(code=4404, reason="peer websocket unavailable")
            return
        upstream_url = f"ws://127.0.0.1:{peer.port + 1001}/events?{urlparse(websocket.request.path).query}"
    try:
        async with websockets.connect(upstream_url) as upstream:
            async def relay(source, target, capture=False):
                async for message in source:
                    if not spectator:
                        peer.last_seen = time.monotonic()
                    if capture:
                        try:
                            manager.record_event(room_id, json.loads(message), peer["name"])
                        except (ValueError, TypeError):
                            pass
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
    # Never log the credential itself: docker logs are readable by anyone with
    # access to the host. Print where it lives and a fingerprint to identify it.
    fingerprint = hashlib.sha256(manager.issuer_token.encode()).hexdigest()[:8]
    print(f"Spectator link issuer credential loaded (sha256 {fingerprint}); read it from "
          f"{REPORT_DIR / '.spectator_issuer_token'} or set SPECTATOR_ISSUER_TOKEN.", flush=True)
    atexit.register(manager.stop_all)
    manager.event_loop = asyncio.get_running_loop()
    for room_id in {peer.get("room_id") for peer in manager.fixed_peers}:
        if room_id:
            for candidate in manager.room_peers(room_id):
                manager.start_collector(room_id, candidate)
    asyncio.create_task(manager.monitor_rooms())
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
