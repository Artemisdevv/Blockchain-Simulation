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

EPOCH_TIME = 60  # kept in sync with consensus/pos/p2p.py's EPOCH_TIME

# Same-machine dev origins only - not a trust boundary by itself (CORS is a
# browser-only concept, curl/Postman ignore it entirely), just stops a
# malicious website open in someone's browser from silently calling this API.
_ALLOWED_ORIGIN_PATTERN = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def create_app(peer, loop, token):
    app = Flask(__name__)
    CORS(app, origins=_ALLOWED_ORIGIN_PATTERN, supports_credentials=False)

    @app.before_request
    def require_token():
        auth = request.headers.get("Authorization", "")
        provided = auth[len("Bearer "):] if auth.startswith("Bearer ") else None
        if not provided or not secrets.compare_digest(provided, token):
            return jsonify({"ok": False, "error": "missing or invalid bearer token"}), 401

    def run_coro(coro, timeout=10):
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

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


def run_api_server(peer, loop, http_port):
    """
    Starts the Flask app in a background daemon thread. Call this from
    inside the peer's running event loop (needs `loop` = the actual running
    loop, e.g. via asyncio.get_running_loop()) so run_coroutine_threadsafe
    targets the right loop.

    Binds to 127.0.0.1 by default - set WEBAPI_HOST=0.0.0.0 explicitly
    (e.g. inside a docker container reached only via published ports) to
    expose it beyond localhost. Auth token is required regardless.
    """
    token = secrets.token_urlsafe(32)
    token_path = f".webapi_token_{http_port}"
    with open(token_path, "w") as f:
        f.write(token)
    try:
        os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)  # best-effort on Windows
    except OSError:
        pass

    host = os.environ.get("WEBAPI_HOST", "127.0.0.1")
    app = create_app(peer, loop, token)

    def _run():
        app.run(host=host, port=http_port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print(f"\nWeb API listening on http://{host}:{http_port}")
    print(f"Auth token (also in {token_path}): {token}")
    print(f"Example: curl -H \"Authorization: Bearer {token}\" http://{host}:{http_port}/chain\n")
    return thread
