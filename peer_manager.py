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

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import KeepTogether, SimpleDocTemplate, Paragraph, Spacer

import requests
from flask import Flask, Response, jsonify, request
import websockets


BASE_PORT = int(os.environ.get("PEER_MANAGER_BASE_PORT", "5100"))
PORT_STEP = int(os.environ.get("PEER_MANAGER_PORT_STEP", "100"))
MAX_PEERS = int(os.environ.get("PEER_MANAGER_MAX_PEERS", "9"))
# Peers whose dashboard has not touched the API for this long are stopped.
IDLE_TIMEOUT = float(os.environ.get("PEER_MANAGER_IDLE_TIMEOUT", "120"))
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
                "MALICIOUS": "n",
                "STAKER": "y",
                # Off by default: with several auto-stakers a node can still fall a
                # block behind. Flip it on per node from the dashboard toggle.
                "AUTO_STAKE": "false",
                "PYTHONUNBUFFERED": "1",
                "WEBAPI_HOST": "0.0.0.0",
                "WEBAPI_TOKEN": token,
            })
            process = self.process_factory(
                [sys.executable, str(PROJECT_ROOT / "start_peer.py")],
                cwd=str(PROJECT_ROOT),
                env=env,
            )
            managed = ManagedPeer(peer_id, name, room_id, port, token, process, time.monotonic())
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
                if peer.token == token and peer.process.poll() is None:
                    return peer.room_id
        for candidate in self.fixed_peers:
            if secrets.compare_digest(str(candidate.get("token", "")), token):
                return candidate.get("room_id")
        return None

    def make_spectator_token(self, room_id):
        payload = b64url(json.dumps({"room_id": room_id, "expires": int(time.time()) + 86400}, separators=(",", ":")).encode())
        signing_key = hashlib.sha256(self.signing_key.encode()).digest()
        signature = hmac.new(signing_key, payload.encode(), hashlib.sha256).digest()
        return f"{payload}.{b64url(signature)}"

    def verify_spectator_token(self, token):
        try:
            payload, signature = token.split(".", 1)
            signing_key = hashlib.sha256(self.signing_key.encode()).digest()
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
                {"peer_id": peer.peer_id, "name": peer.name, "room_id": peer.room_id}
                for peer in manager.peers.values()
            ]
        return jsonify({"peers": peers})

    @app.post("/spectator-links")
    def create_spectator_link():
        data = request.get_json(silent=True) or {}
        room_id = str(data.get("room_id", "")).strip()
        issuer = request.headers.get("X-Spectator-Issuer", "")
        if not secrets.compare_digest(issuer, manager.issuer_token):
            return jsonify({"error": "Valid spectator link issuer credentials are required."}), 403
        if not ROOM_ID_RE.fullmatch(room_id) or not manager.room_peers(room_id):
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
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=letter, title=f"Simulation Run {report['run']['run_id']}", rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    story = [Paragraph("Blockchain Simulation Run Report", styles["Title"]), Spacer(1, 12)]
    run = report["run"]
    def section(title, lines):
        heading = Paragraph(title, styles["Heading2"])
        paragraphs = [Paragraph(escape(str(line)), styles["BodyText"]) for line in lines]
        story.append(KeepTogether([heading, *paragraphs[:3]]))
        story.extend(paragraphs[3:])
        story.append(Spacer(1, 8))
    section("Run Summary", [f"Room: {run['room_id']}", f"Run ID: {run['run_id']}", f"Started (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(run['started_at']))}", f"Ended (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(run['ended_at'])) if run.get('ended_at') else 'Still active at export'}", f"Duration: {run['duration_seconds']} seconds"])
    observed_peers = (report.get("final_state", {}).get("peers") or {}).get("peers", [])
    section("Network", [f"Final peer snapshot source: {report.get('final_state', {}).get('source_peer', 'Unavailable')}", f"Observed peers: {len(observed_peers)}", "Peer names: " + (", ".join(p.get("name", "unknown") for p in observed_peers) or "Unavailable")])
    fmt_time = lambda value: time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(value)) if isinstance(value, (int, float)) else "Unavailable"
    section("Participants", [f"{p.get('name') or 'Unknown'} | first seen {fmt_time(p.get('first_seen_at'))} | last seen {fmt_time(p.get('last_seen_at'))} | {p.get('status', 'observed')}" for p in report.get("participants", [])] or ["No participants recorded."])
    chain = report.get("final_state", {}).get("chain", {}).get("blocks", [])
    txs = [(block, tx) for block in chain for tx in block.get("transactions", [])]
    run_blocks = [e.get("data", {}).get("block", {}) for e in report.get("events", []) if e.get("type") == "block_appended"]
    section("Blockchain", [f"Blocks observed during run: {len(run_blocks)} (event history coverage may be partial)", f"Final chain snapshot height: {len(chain)}", f"Final chain tip: {chain[-1].get('id') if chain else 'Unavailable'}", f"Confirmed transactions in final chain snapshot: {len(txs)}"] + [f"Block {i}: {b.get('id')} | creator {b.get('creator')} | timestamp {b.get('ts')} | stake {b.get('staked_amt', 0)} | tx {len(b.get('transactions', []))}" for i, b in enumerate(run_blocks)] + [f"Transaction {tx.get('id')}: {tx.get('sender')} -> {tx.get('receiver')} | payload {json.dumps(tx.get('payload'), default=str)} | block {block.get('id')}" for block, tx in txs])
    stakes = report.get("final_state", {}).get("stakers", {}).get("stakers", {})
    stake_events = [e for e in report.get("events", []) if e.get("type") == "stake_registered"]
    section("Validators / Stake", [f"Stake change observed: {e.get('data', {}).get('amount')} for {e.get('data', {}).get('staker')}" for e in stake_events] + [f"Current {key}: {value}" for key, value in stakes.items()] or ["No active stake snapshot available."])
    attacks = [e for e in report.get("events", []) if "attack" in e["type"] or e["type"] == "node_slashed"]
    section("Attacks", [json.dumps(e.get("data", {}), default=str) for e in attacks] or ["No attack events were observed by the gateway."])
    section("Events", [f"#{e['sequence']} | {time.strftime('%H:%M:%S', time.gmtime(e['timestamp']))} | {e['type']} | {e.get('source_peer') or 'unknown'}" for e in report.get("events", [])] or ["No live events recorded."])
    final_state = report.get("final_state", {})
    final_mempool = (final_state.get("mempool") or {}).get("transactions", [])
    section("Final State", [f"Snapshot at: {fmt_time(final_state.get('captured_at'))}", f"Final peer names: {', '.join(p.get('name', 'unknown') for p in observed_peers) or 'Unavailable'}", f"Pending transactions at snapshot: {len(final_mempool)}", f"Completeness: {json.dumps(final_state.get('completeness', {}))}", f"Metrics: {json.dumps(final_state.get('metrics', {}), default=str)}", f"Invariants: {json.dumps(final_state.get('invariants', {}), default=str)}", f"Attack Lab state: {json.dumps(final_state.get('attack_lab_state', {}), default=str)}", "Mempool, active peers, and attack state are observed snapshots, not complete historical records."] + [f"Pending transaction {tx.get('id')}: {tx.get('sender')} -> {tx.get('receiver')} | payload {json.dumps(tx.get('payload'), default=str)}" for tx in final_mempool])
    doc.build(story)


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
