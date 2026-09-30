"""
Untrusted input: numbers, JSON bodies and request sizes.

Python's JSON parser accepts NaN and Infinity, and NaN passes every `<= 0` / `> limit`
comparison, so amounts need an explicit finite-number check everywhere they enter: the web
API, peer messages and block/chain validation.
"""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

import consensus.pos.p2p as p2p_mod
from consensus.pos.blockchain_structures import (
    Block, Chain, Transaction, Wallet, is_valid_amount, tx_amount,
)
from consensus.pos.p2p import Peer
from webapi.rate_limit import FailedAuthTracker, RateLimiter
from webapi.server import create_app

NAN = float("nan")
INF = float("inf")


# --- the helper ---

@pytest.mark.parametrize("value", [1, 0.5, 500, 10**12])
def test_is_valid_amount_accepts_positive_finite_numbers(value):
    assert is_valid_amount(value)


@pytest.mark.parametrize("value", [0, -1, NAN, INF, -INF, True, False, None, "5", [5], {"a": 1}])
def test_is_valid_amount_rejects_everything_else(value):
    assert not is_valid_amount(value)


def test_tx_amount_reads_deploy_payload_and_survives_malformed_ones():
    assert tx_amount(SimpleNamespace(receiver="bob", payload=7)) == 7
    assert tx_amount(SimpleNamespace(receiver="deploy", payload=["code", 3])) == 3
    assert tx_amount(SimpleNamespace(receiver="invoke", payload=5)) is None  # not a list
    assert tx_amount(SimpleNamespace(receiver="deploy", payload=[])) is None


# --- block validation ---

def _chain_with_genesis(creator):
    genesis = Block(None, [])
    genesis.creator = creator.public_key_pem
    genesis.sign = creator.private_key.sign(str(genesis).encode())
    Chain.instance = Chain.__new__(Chain)
    Chain.instance.chain = [genesis]
    return genesis


def test_block_with_a_nan_faucet_mint_is_rejected():
    """NaN <= 0 and NaN > 500 are both False, so a faucet-signed NaN mint used to be accepted."""
    from shared_blockchain_structures import FAUCET_SIGNING_KEY

    creator = Wallet()
    original = Chain.instance
    try:
        genesis = _chain_with_genesis(creator)
        mint = Transaction(NAN, "Genesis", creator.public_key_pem, id="nan-mint")
        mint.sign = FAUCET_SIGNING_KEY.sign(str(mint).encode())
        block = Block(genesis.hash, [mint])
        block.creator = creator.public_key_pem
        block.sign = creator.private_key.sign(str(block).encode())

        assert Chain.instance.isValidBlock(block) is False

        # Sanity: the same block with a normal amount is accepted.
        ok = Transaction(50, "Genesis", creator.public_key_pem, id="ok-mint")
        ok.sign = FAUCET_SIGNING_KEY.sign(str(ok).encode())
        good = Block(genesis.hash, [ok])
        good.creator = creator.public_key_pem
        good.sign = creator.private_key.sign(str(good).encode())
        assert Chain.instance.isValidBlock(good) is True
    finally:
        Chain.instance = original


# --- staking ---

def _staker(balance=100):
    peer = Peer.__new__(Peer)
    peer.staker = True
    peer.wallet = Wallet()
    peer.staked_amt = 0
    peer.mem_pool = []
    peer.current_stakes = set()
    peer.current_stakers = {}
    peer.curr_stakers_condition = asyncio.Condition()
    peer.seen_message_ids = set()
    peer.server_connections = set()
    peer.client_connections = set()
    peer.last_epoch_end_ts = datetime.now()
    p2p_mod.Chain.instance = SimpleNamespace(calc_balance=lambda *a, **k: balance)
    return peer


@pytest.mark.parametrize("amount", [INF, -INF, NAN, True, "1e999", None, [1]])
def test_stake_coin_rejects_non_finite_and_odd_amounts(amount):
    original = p2p_mod.Chain.instance
    try:
        result = asyncio.run(_staker().stake_coin(amount))
    finally:
        p2p_mod.Chain.instance = original
    assert result["ok"] is False


# --- web API ---

TOKEN = "test-token"


def _client():
    peer = SimpleNamespace(
        known_peers={}, name_to_public_key_dict={}, mem_pool=[], staker=True, auto_stake=False,
        wallet=SimpleNamespace(public_key_pem="pem"),
    )
    app = create_app(peer, loop=None, token=TOKEN, limiter=RateLimiter(1000, 60), auth_tracker=FailedAuthTracker())
    return app.test_client(), {"Authorization": f"Bearer {TOKEN}"}


def _post(client, headers, path, raw):
    return client.post(path, data=raw, headers={**headers, "Content-Type": "application/json"})


@pytest.mark.parametrize("raw", ['{"receiver": "bob", "amount": NaN}', '{"receiver": "bob", "amount": Infinity}',
                                 '{"receiver": "bob", "amount": 1e999}', '{"receiver": "bob", "amount": true}',
                                 '{"receiver": "bob", "amount": -5}'])
def test_transactions_reject_bad_amounts(raw):
    client, headers = _client()
    assert _post(client, headers, "/transactions", raw).status_code == 400


@pytest.mark.parametrize("raw", ['{"amount": NaN}', '{"amount": Infinity}', '{"amount": -1}', '{"amount": 501}'])
def test_faucet_rejects_bad_amounts(raw):
    client, headers = _client()
    response = _post(client, headers, "/faucet", raw)
    assert response.status_code == 400 and response.json["ok"] is False


def test_latency_rejects_infinity():
    client, headers = _client()
    assert _post(client, headers, "/attack-lab/latency", '{"latency_ms": 1e999}').status_code == 400


@pytest.mark.parametrize("raw", ["[1, 2]", "5", '"text"', "null", "not json"])
def test_non_object_json_bodies_are_a_400_not_a_crash(raw):
    client, headers = _client()
    # (/faucet is left out on purpose: an empty body legitimately means "the default 50 coins".)
    for path in ("/transactions", "/stakes", "/attack-lab/latency", "/attack-lab/partition"):
        assert _post(client, headers, path, raw).status_code < 500, path


def test_oversized_body_is_rejected():
    client, headers = _client()
    assert _post(client, headers, "/transactions", json.dumps({"receiver": "x" * 40000, "amount": 1})).status_code == 413


# --- peer manager ---

def test_peer_manager_rejects_non_object_and_oversized_bodies():
    from peer_manager import PeerManager, create_app as create_manager_app

    manager = PeerManager(process_factory=lambda *a, **k: pytest.fail("must not start a process"))
    client = create_manager_app(manager)[0].test_client()

    assert client.post("/peers", data="[1]", content_type="application/json").status_code == 400
    assert client.post("/peers", data="{}", content_type="application/json").status_code == 400
    big = json.dumps({"name": "a", "room_id": "b" * 70000})
    assert client.post("/peers", data=big, content_type="application/json").status_code == 413
