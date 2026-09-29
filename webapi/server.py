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

from ecdsa import VerifyingKey, BadSignatureError

from consensus.pos.blockchain_structures import Chain
from webapi.rate_limit import RateLimiter, FailedAuthTracker

EPOCH_TIME = 60  # kept in sync with consensus/pos/p2p.py's EPOCH_TIME

# Same-machine dev origins only - not a trust boundary by itself (CORS is a
# browser-only concept, curl/Postman ignore it entirely), just stops a
# malicious website open in someone's browser from silently calling this API.
_ALLOWED_ORIGIN_PATTERN = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def _cors_origins():
    configured = os.environ.get("WEBAPI_CORS_ORIGINS", "").strip()
    if not configured:
        return _ALLOWED_ORIGIN_PATTERN
    return [origin.strip() for origin in configured.split(",") if origin.strip()]

MAX_REQUESTS_PER_MINUTE = 300
MAX_AUTH_FAILURES = 5
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_BLOCK_SECONDS = 300


def _chain_hash_linkage_ok(blocks):
    """Every block's prevHash must match the actual hash of the block before it."""
    for i in range(1, len(blocks)):
        if blocks[i].prevHash != blocks[i - 1].hash:
            return False
    return True


def _chain_proposers_valid(blocks):
    """Every non-genesis block's signature must verify against its claimed creator."""
    for block in blocks[1:]:
        if not block.creator or not block.sign:
            return False
        try:
            VerifyingKey.from_pem(block.creator).verify(block.sign, str(block).encode())
        except (BadSignatureError, Exception):
            return False
    return True


def _chain_supply_conserved(blocks):
    """
    Total coins minted (genesis grant + faucet grants + 6/block miner reward)
    minus stake destroyed by slashing must equal the sum of every wallet's
    balance derived from the same chain - same accounting rules calc_balance()
    uses, just applied to every participant at once instead of one pubkey.
    """
    minted = 0
    slashed_out = 0
    balances = {}

    def add(pubkey, amount):
        if pubkey in ("Genesis", "deploy", "invoke", None):
            return
        balances[pubkey] = balances.get(pubkey, 0) + amount

    for i, block in enumerate(blocks):
        if not block.is_valid:
            continue
        for tx in block.transactions:
            amount = tx.payload[-1] if tx.receiver in ("deploy", "invoke") else tx.payload
            if tx.sender == "Genesis":
                minted += amount
            else:
                add(tx.sender, -amount)
            add(tx.receiver, amount)
        if i != 0 and block.creator:
            minted += 6
            add(block.creator, 6)
        if block.slash_creator and block.creator:
            slashed_out += block.staked_amt
            add(block.creator, -block.staked_amt)

    return sum(balances.values()) == minted - slashed_out


def create_app(peer, loop, token, limiter: RateLimiter, auth_tracker: FailedAuthTracker):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # reject oversized request bodies
    CORS(app, origins=_cors_origins(), supports_credentials=False)

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

        return jsonify({
            "honest_consensus": _chain_hash_linkage_ok(blocks),
            "supply_conserved": _chain_supply_conserved(blocks),
            "valid_proposers": _chain_proposers_valid(blocks),
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

        blocks_dicts = Chain.instance.to_block_dict_list()

        # Support ?height=N or ?limit=N for Time-Travel Scrubber
        height = request.args.get("height", type=int)
        if height is not None and height >= 0:
            blocks_dicts = blocks_dicts[:height + 1]

        return jsonify({"blocks": blocks_dicts})

    @app.get("/metrics")
    def get_metrics():
        if not Chain.instance:
            return jsonify({
                "blocks_count": 0,
                "total_transactions": 0,
                "total_staked": 0,
                "mempool_count": len(peer.mem_pool),
                "peer_count": len(peer.known_peers),
                "avg_block_time_sec": 30,
                "room_id": getattr(peer, "room_id", "demo")
            })

        blocks = Chain.instance.chain
        blocks_count = len(blocks)
        total_txs = sum(len(b.transactions) for b in blocks)
        total_staked = sum(peer.current_stakers.values()) if peer.current_stakers else 0

        avg_block_time = 30.0
        if blocks_count > 1:
            time_diff = blocks[-1].ts - blocks[0].ts
            if time_diff > 0:
                avg_block_time = round(time_diff / (blocks_count - 1), 1)

        return jsonify({
            "blocks_count": blocks_count,
            "total_transactions": total_txs,
            "total_staked": total_staked,
            "mempool_count": len(peer.mem_pool),
            "peer_count": len(peer.known_peers),
            "avg_block_time_sec": avg_block_time,
            "room_id": getattr(peer, "room_id", "demo")
        })

    @app.get("/peers")
    def get_peers():
        peers = [
            {"host": h, "port": p, "name": n, "public_key": pk}
            for (h, p), (n, pk) in peer.known_peers.items()
        ]
        peers.append({
            "host": peer.host,
            "port": peer.port,
            "name": peer.name,
            "public_key": peer.wallet.public_key_pem,
        })
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
            return jsonify({"public_key": peer.wallet.public_key_pem, "balance": 0, "pending_income": 0})
        raw_balance = Chain.instance.calc_balance(
            peer.wallet.public_key_pem, peer.mem_pool, list(peer.current_stakes)
        )
        is_slashed = any(
            b.slash_creator and b.creator == peer.wallet.public_key_pem
            for b in Chain.instance.chain
        )

        # Incoming coins sitting in mempool aren't spendable/stakeable yet - not
        # mined, so not final. Surfaced separately so the UI can show it without
        # letting the user try to spend/stake against money they don't have yet
        # (matches /transactions and /stakes, which validate against raw_balance).
        pending_income = sum(
            tx.payload for tx in peer.mem_pool
            if tx.receiver == peer.wallet.public_key_pem
        )

        spendable_balance = raw_balance if is_slashed else max(0, raw_balance)
        return jsonify({
            "public_key": peer.wallet.public_key_pem,
            "balance": spendable_balance,
            "pending_income": pending_income,
        })

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

    faucet_limiter = RateLimiter(max_requests=10, window_seconds=3600)

    @app.post("/faucet")
    def post_faucet():
        client_ip = request.remote_addr or "unknown"
        if not faucet_limiter.allow(client_ip):
            return jsonify({
                "ok": False,
                "error": "Faucet rate limit exceeded: Maximum 10 faucet requests per hour."
            }), 429

        data = request.get_json(force=True, silent=True) or {}
        amount = data.get("amount", 50)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 50.0

        if amount <= 0 or amount > 500:
            return jsonify({"ok": False, "error": "Amount must be between 1 and 500"}), 400

        from consensus.pos.blockchain_structures import Transaction
        from shared_blockchain_structures import FAUCET_SIGNING_KEY
        import base64, json

        faucet_tx = Transaction(amount, "Genesis", peer.wallet.public_key_pem)
        # "Genesis" isn't a real keypair - sign with the well-known faucet
        # key so other peers can verify this mint instead of trusting the
        # sender string alone (see FAUCET_SIGNING_KEY's docstring).
        faucet_tx.sign = FAUCET_SIGNING_KEY.sign(str(faucet_tx).encode())

        async def _add_and_broadcast_faucet():
            async with peer.mem_pool_lock:
                peer.mem_pool.append(faucet_tx)
            pkt = {
                "type": "new_tx",
                "id": faucet_tx.id,
                "transaction": json.dumps(faucet_tx.to_dict()),
                "sign": base64.b64encode(faucet_tx.sign).decode(),
                "sender_pem": "Genesis"
            }
            # create_and_broadcast_tx registers its message id in
            # seen_message_ids *before* broadcasting, so handle_messages'
            # top-level "if id in self.seen_message_ids: return" catches
            # it when a peer relays it back to us (handle_messages' new_tx
            # branch always relays onward - in a full mesh that means it
            # comes right back). This was missing here, so a relayed
            # faucet broadcast would sail past that guard and get
            # double-appended to our own mempool - doubling the amount
            # shown as pending everywhere until it's mined.
            peer.seen_message_ids.add(pkt["id"])
            await peer.broadcast_message(pkt)

        run_coro(_add_and_broadcast_faucet())

        new_balance = 0
        if Chain.instance:
            new_balance = max(0, Chain.instance.calc_balance(
                peer.wallet.public_key_pem, peer.mem_pool, list(peer.current_stakes)
            ))

        return jsonify({
            "ok": True,
            "added_amount": amount,
            "new_balance": new_balance,
            "transaction_id": faucet_tx.id
        })

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
