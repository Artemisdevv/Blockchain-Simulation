"""
A node that followed one of a double-signer's two conflicting blocks must
still catch up with the rest of the network.

The chain-sync handler used to treat "same creator, different block at one
height" as slash-only: the double-signer was slashed but the node kept its own
branch. Every later block builds on the other branch, so it failed with
"Hash Problem" forever while the rest of the network moved on (or, if it was
the node ahead, the others never adopted its longer chain).
"""
import asyncio
import base64

from consensus.pos import p2p as p2p_module
from consensus.pos.blockchain_structures import Block, Chain, Stake, Transaction, Wallet
from consensus.pos.p2p import Peer


def _signed_block(prev_hash, creator, txs=(), stake_amt=0, staker=None):
    block = Block(prev_hash, list(txs))
    block.creator = creator.public_key_pem
    block.staked_amt = stake_amt
    if staker is not None and stake_amt:
        stake = Stake(staker.public_key_pem, stake_amt)
        stake.sign = staker.private_key.sign(str(stake).encode())
        block.stakers = [stake]
    block.sign = creator.private_key.sign(str(block).encode())
    return block


def _tx(sender, receiver, amount):
    tx = Transaction(amount, sender.public_key_pem, receiver.public_key_pem)
    tx.sign = sender.private_key.sign(str(tx).encode())
    return tx


def _packet(blocks):
    chain = Chain.__new__(Chain)
    chain.chain = blocks
    return {"type": "chain", "id": "chain-1", "chain": Chain.to_block_dict_list(chain)}


def _peer(local_chain):
    peer = Peer.__new__(Peer)
    peer.seen_message_ids = set()
    peer.mem_pool = []
    peer.mem_pool_lock = asyncio.Lock()
    peer.file_hashes = {}
    peer.file_hashes_lock = asyncio.Lock()
    peer.activate_disk_save = "n"
    peer.server_connections = set()
    peer.client_connections = set()
    peer.event_subscribers = set()
    peer.chain = local_chain
    return peer


def _run(peer, packet):
    async def go():
        await peer.handle_messages(None, packet)
        await asyncio.sleep(0)  # let the fire-and-forget event tasks finish

    asyncio.run(go())


def _fork_fixture():
    honest, mallory, victim_a, victim_b = Wallet(), Wallet(), Wallet(), Wallet()
    genesis = _signed_block(None, honest)
    # Mallory's two conflicting blocks on the same parent.
    on_a = _signed_block(genesis.hash, mallory, [_tx(mallory, victim_a, 30)], 10, mallory)
    on_b = _signed_block(genesis.hash, mallory, [_tx(mallory, victim_b, 20)], 10, mallory)
    assert on_a.hash != on_b.hash
    # The rest of the network built on `on_a` and is a block ahead.
    ahead = _signed_block(on_a.hash, honest, stake_amt=25, staker=honest)
    return genesis, on_a, on_b, ahead


def _install(monkeypatch, blocks):
    Chain.instance = None
    monkeypatch.setattr(p2p_module, "isvalidChain", lambda block_list: True)
    local = Chain(blockList=list(blocks))
    monkeypatch.setattr(p2p_module.Chain, "instance", local)
    return local


def test_node_on_the_losing_branch_adopts_the_longer_chain(monkeypatch):
    genesis, on_a, on_b, ahead = _fork_fixture()
    local = _install(monkeypatch, [genesis, on_b])  # stuck on Mallory's other block
    peer = _peer(local)

    _run(peer, _packet([genesis, on_a, ahead]))

    assert [b.hash for b in local.chain] == [genesis.hash, on_a.hash, ahead.hash]
    assert local.chain[1].slash_creator and not local.chain[1].is_valid, "the double-signed block stays slashed"


def test_node_ahead_keeps_its_longer_chain_but_still_slashes(monkeypatch):
    genesis, on_a, on_b, ahead = _fork_fixture()
    local = _install(monkeypatch, [genesis, on_a, ahead])
    peer = _peer(local)

    _run(peer, _packet([genesis, on_b]))

    assert [b.hash for b in local.chain] == [genesis.hash, on_a.hash, ahead.hash]
    assert local.chain[1].slash_creator
