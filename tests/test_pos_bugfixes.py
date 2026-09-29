"""
Regression tests for the three PoS consensus bugs fixed in issue #3.
Run: pytest test_pos_bugfixes.py -v
"""
import asyncio
import pytest

from consensus.pos.blockchain_structures import (
    Transaction, Stake, Block, Wallet, transaction_exists_in_block_list
)
from consensus.pos.p2p import Peer


def make_wallet():
    return Wallet()


def make_tx(wallet, tx_id, payload=1, receiver="someone"):
    tx = Transaction(payload, wallet.public_key_pem, receiver, id=tx_id)
    tx.sign = wallet.private_key.sign(str(tx).encode())
    return tx


def make_block(prev_hash, transactions):
    return Block(prev_hash, transactions)


# --- Bug 2: transaction_exists_in_block_list off-by-one ---

def test_duplicate_tx_in_immediately_preceding_block_is_caught():
    """
    Before the fix, range(idx-1) skipped checking blockList[idx-1] -
    a duplicate transaction placed in the block right before the one
    being validated slipped through undetected.
    """
    w = make_wallet()
    dup_tx = make_tx(w, "dup-1")

    block0 = make_block(None, [dup_tx])
    block1 = make_block("hash0", [dup_tx])  # same tx id reused in adjacent block

    block_list = [block0, block1]

    # idx=1 means "is dup_tx a duplicate of anything before block_list[1]?"
    # block_list[0] holds it - must be detected.
    assert transaction_exists_in_block_list(block_list, dup_tx, 1) is False


def test_non_duplicate_tx_not_flagged():
    w = make_wallet()
    tx_a = make_tx(w, "a")
    tx_b = make_tx(w, "b")

    block0 = make_block(None, [tx_a])
    block1 = make_block("hash0", [tx_b])
    block_list = [block0, block1]

    result = transaction_exists_in_block_list(block_list, tx_b, 1)
    assert result is None or result is True  # not a false positive duplicate flag


# --- Bug 3: verify_and_slash signature verified against wrong block content ---

def test_verify_and_slash_detects_genuine_double_sign():
    """
    Before the fix, sign1 was verified against block2's content instead of
    block1's, so a genuinely double-signed block pair (same creator, two
    different blocks at the same height, both validly signed by them) would
    incorrectly fail block1's signature check.
    """
    creator = make_wallet()

    tx1 = make_tx(creator, "tx1")
    tx2 = make_tx(creator, "tx2")

    block1 = make_block("same-prev-hash", [tx1])
    block1.creator = creator.public_key_pem
    block1.sign = creator.private_key.sign(str(block1).encode())

    block2 = make_block("same-prev-hash", [tx2])
    block2.creator = creator.public_key_pem
    block2.sign = creator.private_key.sign(str(block2).encode())

    peer = Peer.__new__(Peer)  # skip full __init__ (network/disk setup not needed)

    class FakeChain:
        chain = [block1]
        instance = None
    FakeChain.instance = FakeChain

    import consensus.pos.p2p as p2p_module
    original_chain = p2p_module.Chain.instance
    p2p_module.Chain.instance = FakeChain
    try:
        peer.server_connections = set()
        peer.client_connections = set()
        asyncio.run(peer.verify_and_slash(block1, block2, 0, [block1]))
    finally:
        p2p_module.Chain.instance = original_chain

    assert FakeChain.chain[0].is_valid is False
    assert FakeChain.chain[0].slash_creator is True


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
