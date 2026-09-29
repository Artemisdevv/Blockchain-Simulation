"""
Regression tests for Peer.stake_coin() - the staking logic extracted out of
the CLI menu (option 9) so the web API (webapi/server.py POST /stakes) can
reuse the same epoch-timing/balance rules instead of duplicating them.
"""
import asyncio
import pytest
from datetime import datetime

import consensus.pos.p2p as p2p_mod
from consensus.pos.p2p import Peer
from consensus.pos.blockchain_structures import Wallet


def make_peer(balance=5):
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

    class FakeChain:
        @staticmethod
        def calc_balance(*a, **k):
            return balance

    p2p_mod.Chain.instance = FakeChain
    return peer


def test_non_staker_rejected():
    peer = make_peer()
    peer.staker = False
    result = asyncio.run(peer.stake_coin(10))
    assert result == {"ok": False, "error": "node is not a staker"}


def test_amount_exceeds_balance_rejected():
    peer = make_peer(balance=5)
    result = asyncio.run(peer.stake_coin(10))
    assert result["ok"] is False
    assert "insufficient" in result["error"]


def test_invalid_amount_rejected():
    peer = make_peer(balance=5)
    result = asyncio.run(peer.stake_coin("not-a-number"))
    assert result["ok"] is False
    assert "valid integer" in result["error"]


def test_non_positive_amount_rejected():
    peer = make_peer(balance=5)
    result = asyncio.run(peer.stake_coin(0))
    assert result["ok"] is False
    assert "positive" in result["error"]


def test_double_stake_in_same_epoch_rejected():
    peer = make_peer(balance=100)
    peer.staked_amt = 10  # already staked this epoch
    result = asyncio.run(peer.stake_coin(5))
    assert result == {"ok": False, "error": "already staked this epoch"}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
