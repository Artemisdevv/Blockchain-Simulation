"""
Regression tests for the three PoS consensus bugs fixed in issue #3.
Run: pytest test_pos_bugfixes.py -v
"""
import asyncio
import base64
import json
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


# --- Bug 4 (issue #19): block production required a pending transaction ---

def test_block_production_does_not_require_pending_transactions():
    """
    Before the fix, create_blocks() bailed out (clearing the epoch's
    stakers, never running the VRF lottery) whenever mempool had no
    pending transactions - so a lone staker with nothing to send could
    never actually produce a block, and the chain could never advance.
    """
    creator = make_wallet()

    genesis = make_block(None, [])
    genesis.creator = creator.public_key_pem
    genesis.sign = creator.private_key.sign(str(genesis).encode())

    class FakeChain:
        chain = [genesis]
        instance = None

        @property
        def lastBlock(self):
            return self.chain[-1]

        def epoch_seed(self):
            return "fixed-test-seed"

        def transaction_exists_in_chain(self, tx):
            return False
    FakeChain.instance = FakeChain()

    import consensus.pos.p2p as p2p_module
    original_chain = p2p_module.Chain.instance
    p2p_module.Chain.instance = FakeChain.instance
    try:
        peer = Peer.__new__(Peer)
        peer.staker = True
        peer.wallet = creator
        peer.mem_pool = []  # no pending transactions
        peer.mem_pool_lock = asyncio.Lock()
        peer.file_hashes = {}
        peer.file_hashes_lock = asyncio.Lock()
        peer.current_stakers = {creator.public_key_pem: 50}
        peer.current_stakes = set()
        peer.staked_amt = 50  # sole staker -> deterministically wins the VRF
        peer.curr_stakers_condition = asyncio.Condition()
        peer.last_epoch_end_ts = None
        peer.activate_disk_save = "n"
        peer.server_connections = set()
        peer.client_connections = set()
        peer.seen_message_ids = set()

        asyncio.run(peer.create_blocks(0))
    finally:
        p2p_module.Chain.instance = original_chain

    assert len(FakeChain.instance.chain) == 2, (
        "sole staker with no pending transactions should still win the "
        "lottery and produce an (empty) block"
    )
    assert FakeChain.instance.chain[1].creator == creator.public_key_pem


# --- Bug 5: losing the VRF lottery never cleared stake state ---

def test_losing_the_vrf_lottery_clears_stake_state():
    """
    Before the fix, the "You've lost" branch only reset staked_amt - it
    never cleared current_stakers/current_stakes or bumped
    last_epoch_end_ts, unlike every other exit path in create_blocks().
    A losing staker's own Stake object stayed in current_stakes forever,
    permanently deducting that amount from calc_balance() on every future
    call (and inflating total_stake for every future epoch's threshold),
    even though the coins were never actually spent.
    """
    loser = make_wallet()
    whale = make_wallet()

    genesis = make_block(None, [])
    genesis.creator = loser.public_key_pem
    genesis.sign = loser.private_key.sign(str(genesis).encode())

    class FakeChain:
        chain = [genesis]
        instance = None

        @property
        def lastBlock(self):
            return self.chain[-1]

        def epoch_seed(self):
            return "fixed-test-seed"

        def transaction_exists_in_chain(self, tx):
            return False
    FakeChain.instance = FakeChain()

    import consensus.pos.p2p as p2p_module
    original_chain = p2p_module.Chain.instance
    p2p_module.Chain.instance = FakeChain.instance
    try:
        peer = Peer.__new__(Peer)
        peer.staker = True
        peer.wallet = loser
        peer.mem_pool = []
        peer.mem_pool_lock = asyncio.Lock()
        peer.file_hashes = {}
        peer.file_hashes_lock = asyncio.Lock()
        # Loser holds a vanishingly small share of total stake, so the VRF
        # threshold is astronomically close to zero - a loss is certain
        # without needing to mock the signature/hash.
        peer.current_stakers = {
            loser.public_key_pem: 1,
            whale.public_key_pem: 10 ** 30,
        }
        peer.current_stakes = {"placeholder-stake-object"}
        peer.staked_amt = 1
        peer.curr_stakers_condition = asyncio.Condition()
        peer.last_epoch_end_ts = None
        peer.activate_disk_save = "n"
        peer.server_connections = set()
        peer.client_connections = set()
        peer.seen_message_ids = set()

        asyncio.run(peer.create_blocks(0))

        assert peer.current_stakers == {}, "losing must clear current_stakers"
        assert peer.current_stakes == set(), "losing must clear current_stakes"
        assert peer.staked_amt == 0
        assert peer.last_epoch_end_ts is not None, "losing must start the next epoch's timer"
        assert len(FakeChain.instance.chain) == 1, "the loser must not have produced a block"
    finally:
        p2p_module.Chain.instance = original_chain


# --- Bug 6: Genesis-sender (faucet) transactions crashed block/chain validation ---

def _genesis_and_chain_instance(creator):
    from consensus.pos.blockchain_structures import Chain as PosChain
    genesis = make_block(None, [])
    genesis.creator = creator.public_key_pem
    genesis.sign = creator.private_key.sign(str(genesis).encode())
    PosChain.instance = PosChain.__new__(PosChain)
    PosChain.instance.chain = [genesis]
    return PosChain, genesis


def test_isvalidblock_accepts_genesis_mint_transaction():
    """
    Before the fix, isValidBlock() unconditionally did
    VerifyingKey.from_pem(transaction.sender) for every transaction -
    "Genesis" isn't valid PEM/base64 data, so any block containing a
    faucet-minted transaction crashed validation with an unhandled
    binascii.Error instead of being accepted or cleanly rejected.

    Reproduced live: bob's connection-handling coroutine crashed with
    "binascii.Error: Incorrect padding" the moment alice's chain included
    a faucet transaction, and the crash cascaded into other peers
    failing to connect to bob at all.
    """
    from shared_blockchain_structures import FAUCET_SIGNING_KEY

    creator = make_wallet()
    original_instance = None
    try:
        PosChain, genesis = _genesis_and_chain_instance(creator)
        original_instance = PosChain.instance

        mint_tx = Transaction(50, "Genesis", creator.public_key_pem, id="mint-1")
        mint_tx.sign = FAUCET_SIGNING_KEY.sign(str(mint_tx).encode())
        block2 = make_block(genesis.hash, [mint_tx])
        block2.creator = creator.public_key_pem
        block2.sign = creator.private_key.sign(str(block2).encode())

        assert PosChain.instance.isValidBlock(block2) is True
    finally:
        if original_instance is not None:
            PosChain.instance = original_instance


def test_isvalidblock_rejects_oversized_genesis_mint():
    """
    A real faucet signature must not become an unbounded minting hole -
    even correctly signed by the faucet key, an amount over the faucet
    endpoint's own 500-coin cap must still be rejected.
    """
    from shared_blockchain_structures import FAUCET_SIGNING_KEY

    creator = make_wallet()
    original_instance = None
    try:
        PosChain, genesis = _genesis_and_chain_instance(creator)
        original_instance = PosChain.instance

        fake_mint = Transaction(10 ** 9, "Genesis", creator.public_key_pem, id="mint-2")
        fake_mint.sign = FAUCET_SIGNING_KEY.sign(str(fake_mint).encode())
        block2 = make_block(genesis.hash, [fake_mint])
        block2.creator = creator.public_key_pem
        block2.sign = creator.private_key.sign(str(block2).encode())

        assert PosChain.instance.isValidBlock(block2) is False
    finally:
        if original_instance is not None:
            PosChain.instance = original_instance


def test_isvalidblock_rejects_forged_genesis_mint_without_faucet_signature():
    """
    Security fix: "Genesis" as a sender is just a string - without this
    check, any peer could broadcast a "Genesis"-sender transaction with no
    real authorization and mint themselves free coins. A valid-range
    amount (<=500) must still be rejected if it isn't actually signed by
    the well-known faucet key.
    """
    creator = make_wallet()
    attacker = make_wallet()  # some other real keypair, NOT the faucet's
    original_instance = None
    try:
        PosChain, genesis = _genesis_and_chain_instance(creator)
        original_instance = PosChain.instance

        forged_mint = Transaction(50, "Genesis", attacker.public_key_pem, id="forged-1")
        forged_mint.sign = attacker.private_key.sign(str(forged_mint).encode())
        block2 = make_block(genesis.hash, [forged_mint])
        block2.creator = creator.public_key_pem
        block2.sign = creator.private_key.sign(str(block2).encode())

        assert PosChain.instance.isValidBlock(block2) is False

        # Completely unsigned must also be rejected, not just wrongly-signed.
        unsigned_mint = Transaction(50, "Genesis", attacker.public_key_pem, id="forged-2")
        block3 = make_block(genesis.hash, [unsigned_mint])
        block3.creator = creator.public_key_pem
        block3.sign = creator.private_key.sign(str(block3).encode())

        assert PosChain.instance.isValidBlock(block3) is False
    finally:
        if original_instance is not None:
            PosChain.instance = original_instance


# --- Bug 7: a looped-back new_tx broadcast could double-append into our own mempool ---

def test_new_tx_handler_does_not_double_append_when_already_in_own_mempool():
    """
    Reproduces the live "+50 shows as +100 pending" bug. handle_messages'
    new_tx branch ends by relaying every valid transaction onward
    (await self.broadcast_message(msg)) - in a full mesh, alice sends to
    bob, bob relays to everyone including alice. The faucet handler
    appends its mint to its own mempool directly (bypassing
    handle_messages/seen_message_ids entirely) and never registered its
    own message id in seen_message_ids before broadcasting, unlike
    create_and_broadcast_tx, which does - so when bob's relay brings it
    back to alice, her own top-level "already seen" guard doesn't
    recognize it and lets it through. transaction_exists_in_chain() only
    checks confirmed transactions, not the mempool, so without an
    explicit mempool-id check the relayed copy gets appended a second
    time, doubling everything derived from it (pending balance, mempool
    totals) until it's mined.
    """
    from shared_blockchain_structures import FAUCET_SIGNING_KEY

    receiver = make_wallet()
    genesis = make_block(None, [])
    genesis.creator = receiver.public_key_pem
    genesis.sign = receiver.private_key.sign(str(genesis).encode())

    class FakeChain:
        instance = None
        def __init__(self):
            self.chain = [genesis]
        def transaction_exists_in_chain(self, tx):
            return False
    FakeChain.instance = FakeChain()

    import consensus.pos.p2p as p2p_module
    original_chain = p2p_module.Chain.instance
    p2p_module.Chain.instance = FakeChain.instance
    try:
        peer = Peer.__new__(Peer)
        peer.name = "alice"
        peer.mem_pool_lock = asyncio.Lock()
        peer.seen_message_ids = set()
        peer.current_stakes = set()
        peer.server_connections = set()
        peer.client_connections = set()

        mint_tx = Transaction(50, "Genesis", receiver.public_key_pem, id="loop-1")
        mint_tx.sign = FAUCET_SIGNING_KEY.sign(str(mint_tx).encode())

        # The faucet's local append - happens outside handle_messages, so
        # it never touches seen_message_ids.
        peer.mem_pool = [mint_tx]

        pkt = {
            "type": "new_tx",
            "id": "some-other-envelope-id",  # simulates the missing seen_message_ids registration
            "transaction": json.dumps(mint_tx.to_dict()),
            "sign": base64.b64encode(mint_tx.sign).decode(),
            "sender_pem": "Genesis",
        }

        asyncio.run(peer.handle_messages(None, pkt))

        assert len(peer.mem_pool) == 1
    finally:
        p2p_module.Chain.instance = original_chain


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
