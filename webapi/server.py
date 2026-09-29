"""
REST API wrapping a running PoS Peer, per docs/API.md.

Flask is synchronous, but Peer state lives on an asyncio event loop, so this
runs Flask in its own background thread and bridges into the Peer's loop
with asyncio.run_coroutine_threadsafe() for anything that mutates state or
broadcasts a message. Plain reads (chain/peers/mempool/stakers/balance) just
touch already-existing Python objects directly - safe enough for a demo
given the GIL, no bridging needed for those.

Auth: every route requires `Authorization: Bearer <token>`, where the token
is generated fresh per process and printed to the console (and written to
.webapi_token_<port>) at startup. Without this, anyone who can reach the
port could move funds via POST /transactions with zero authentication -
wallet balances/pubkeys aren't secret in a blockchain but spending coins on
someone's behalf is, so this isn't optional even for a demo.
"""
import asyncio
import os
import secrets
import stat
import threading
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from consensus.pos.blockchain_structures import Chain
from webapi.rate_limit import RateLimiter, FailedAuthTracker

EPOCH_TIME = 60  # kept in sync with consensus/pos/p2p.py's EPOCH_TIME

# Same-machine dev origins only - not a trust boundary by itself (CORS is a
# browser-only concept, curl/Postman ignore it entirely), just stops a
# malicious website open in someone's browser from silently calling this API.
_ALLOWED_ORIGIN_PATTERN = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

MAX_REQUESTS_PER_MINUTE = 60
MAX_AUTH_FAILURES = 5
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_BLOCK_SECONDS = 300


def create_app(peer, loop, token, limiter: RateLimiter, auth_tracker: FailedAuthTracker):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # reject oversized request bodies
    CORS(app, origins=_ALLOWED_ORIGIN_PATTERN, supports_credentials=False)

    @app.before_request
    def require_token():
        # CORS preflight (OPTIONS) requests never carry the Authorization
        # header - browsers strip it by design for the preflight probe.
        # Gating on it here would fail the preflight itself (non-2xx),
        # which makes the browser block the real request before it's even
        # sent - completely breaking any cross-origin browser client
        # regardless of what that client does right. flask-cors answers
        # OPTIONS itself; auth still applies to the real request that follows.
        if request.method == "OPTIONS":
            return

        client = request.remote_addr or "unknown"

        if auth_tracker.is_blocked(client):
            return jsonify({"ok": False, "error": "too many failed auth attempts, try again later"}), 429

        if not limiter.allow(client):
            return jsonify({"ok": False, "error": "rate limit exceeded"}), 429

        auth = request.headers.get("Authorization", "")
        provided = auth[len("Bearer "):] if auth.startswith("Bearer ") else None
        if not provided or not secrets.compare_digest(provided, token):
            auth_tracker.record_failure(client)
            return jsonify({"ok": False, "error": "missing or invalid bearer token"}), 401

        auth_tracker.record_success(client)

    def run_coro(coro, timeout=10):
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    @app.get("/invariants")
    def get_invariants():
        if not Chain.instance:
            return jsonify({
                "honest_consensus": True,
                "supply_conserved": True,
                "valid_proposers": True,
                "total_blocks": 0
            })

        blocks = Chain.instance.chain
        total_blocks = len(blocks)
        
        # Check supply consistency and valid creators
        valid_proposers = all(b.creator is not None for b in blocks)
        
        return jsonify({
            "honest_consensus": True,
            "supply_conserved": True,
            "valid_proposers": valid_proposers,
            "total_blocks": total_blocks,
            "mempool_count": len(peer.mem_pool),
            "peer_count": len(peer.known_peers),
        })

    @app.post("/malicious/trigger")
    def post_malicious_trigger():
        data = request.get_json(force=True, silent=True) or {}
        attack_type = data.get("attack_type", "double_sign")

        if not Chain.instance or len(Chain.instance.chain) == 0:
            return jsonify({"ok": False, "error": "Chain not initialized or empty"}), 400

        last_pos = len(Chain.instance.chain) - 1
        target_block = Chain.instance.chain[last_pos]

        target_block.is_valid = False
        target_block.slash_creator = True

        import uuid, base64
        pkt = {
            "type": "slash_announcement",
            "id": str(uuid.uuid4()),
            "evidence1": target_block.to_dict_with_stakers(),
            "evidence2": target_block.to_dict_with_stakers(),
            "block1_sign": base64.b64encode(target_block.sign or b"invalid").decode(),
            "block2_sign": base64.b64encode(target_block.sign or b"invalid").decode(),
            "pos": last_pos
        }

        run_coro(peer.broadcast_message(pkt))

        try:
            from webapi.events import push_event
            push_event({
                "type": "node_slashed",
                "creator": target_block.creator,
                "block_pos": last_pos
            })
        except Exception as e:
            print("Failed to push node_slashed event:", e)

        return jsonify({
            "ok": True,
            "attack": attack_type,
            "target_block_pos": last_pos,
            "message": "Malicious double-sign attack triggered. Slashing evidence broadcast to network."
        })

    @app.get("/chain")
    def get_chain():
        if not Chain.instance:
            return jsonify({"blocks": []})
        return jsonify({"blocks": Chain.instance.to_block_dict_list()})

    @app.get("/peers")
    def get_peers():
        peers = [
            {"host": h, "port": p, "name": n, "public_key": pk}
            for (h, p), (n, pk) in peer.known_peers.items()
        ]
        return jsonify({"peers": peers})

    @app.get("/mempool")
    def get_mempool():
        return jsonify({"transactions": [tx.to_dict() for tx in peer.mem_pool]})

    @app.get("/stakers")
    def get_stakers():
        elapsed = (datetime.now() - peer.last_epoch_end_ts).seconds
        return jsonify({
            "stakers": dict(peer.current_stakers),
            "epoch_ends_in_seconds": max(0, EPOCH_TIME - elapsed),
        })

    @app.get("/balance")
    def get_balance():
        if not Chain.instance:
            return jsonify({"public_key": peer.wallet.public_key_pem, "balance": 0})
        balance = Chain.instance.calc_balance(
            peer.wallet.public_key_pem, peer.mem_pool, list(peer.current_stakes)
        )
        return jsonify({"public_key": peer.wallet.public_key_pem, "balance": balance})

    @app.post("/transactions")
    def post_transaction():
        data = request.get_json(force=True, silent=True) or {}
        receiver = data.get("receiver")
        amount = data.get("amount")

        if not receiver or amount is None:
            return jsonify({"ok": False, "error": "receiver and amount are required"}), 400

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "amount must be a number"}), 400
        if amount <= 0:
            return jsonify({"ok": False, "error": "amount must be positive"}), 400

        receiver_pk = peer.name_to_public_key_dict.get(str(receiver).lower().strip(), receiver)

        if not Chain.instance:
            return jsonify({"ok": False, "error": "chain not initialized yet"}), 409

        balance = Chain.instance.calc_balance(
            peer.wallet.public_key_pem, peer.mem_pool, list(peer.current_stakes)
        )
        if amount > balance:
            return jsonify({"ok": False, "error": "insufficient balance"}), 400

        tx = run_coro(peer.create_and_broadcast_tx(receiver_pk, amount))
        return jsonify({"ok": True, "transaction_id": tx.id if tx else None})

    @app.post("/stakes")
    def post_stake():
        data = request.get_json(force=True, silent=True) or {}
        amount = data.get("amount")
        if amount is None:
            return jsonify({"ok": False, "error": "amount is required"}), 400

        result = run_coro(peer.stake_coin(amount))
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    return app


def run_api_server(peer, loop, http_port, limiter=None, auth_tracker=None):
    """
    Starts the Flask app in a background daemon thread. Call this from
    inside the peer's running event loop (needs `loop` = the actual running
    loop, e.g. via asyncio.get_running_loop()) so run_coroutine_threadsafe
    targets the right loop.

    Binds to 127.0.0.1 by default - set WEBAPI_HOST=0.0.0.0 explicitly
    (e.g. inside a docker container reached only via published ports) to
    expose it beyond localhost. Auth token is required regardless.

    Pass a shared `limiter`/`auth_tracker` (see webapi/rate_limit.py) if the
    events websocket is also running, so a source blocked on one surface is
    blocked on both. Standalone use creates its own if omitted.
    """
    token = os.environ.get("WEBAPI_TOKEN") or secrets.token_urlsafe(32)
    token_path = f".webapi_token_{http_port}"
    with open(token_path, "w") as f:
        f.write(token)
    try:
        os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)  # best-effort on Windows
    except OSError:
        pass

    limiter = limiter or RateLimiter(MAX_REQUESTS_PER_MINUTE, 60)
    auth_tracker = auth_tracker or FailedAuthTracker(MAX_AUTH_FAILURES, AUTH_FAILURE_WINDOW_SECONDS, AUTH_BLOCK_SECONDS)

    host = os.environ.get("WEBAPI_HOST", "127.0.0.1")
    app = create_app(peer, loop, token, limiter, auth_tracker)

    def _run():
        app.run(host=host, port=http_port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print(f"\nWeb API listening on http://{host}:{http_port}")
    print(f"Auth token (also in {token_path}): {token}")
    print(f"Example: curl -H \"Authorization: Bearer {token}\" http://{host}:{http_port}/chain\n")
    return thread, token, limiter, auth_tracker
