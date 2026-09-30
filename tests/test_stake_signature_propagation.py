"""
A stake learned from a stake_announcement must keep its signature.

The leader packs its current_stakes into the block it mints. Block
serialisation drops the "sign" of an unsigned stake and block parsing drops any
stake without one, so a stake stored without its signature vanished from the
block's stake list. Receivers that still knew the stake then rejected the block
("stake list omits or alters a known stake"), while receivers that had already
cleared their stakes accepted it - the chain forked with several stakers.
"""
import asyncio
import base64

from consensus.pos import p2p as p2p_module
from consensus.pos.blockchain_structures import Block, Stake, Wallet
from consensus.pos.p2p import Peer


class _Chain:
    @staticmethod
    def calc_balance(*_args):
        return 1000


def _receiver():
    peer = Peer.__new__(Peer)
    peer.current_stakers = {}
    peer.current_stakes = set()
    peer.curr_stakers_condition = asyncio.Condition()
    peer.mem_pool = []
    peer.seen_message_ids = set()
    peer.server_connections = set()
    peer.client_connections = set()
    peer.event_subscribers = set()
    return peer


def _announcement(wallet, amt):
    stake = Stake(wallet.public_key_pem, amt)
    sign = wallet.private_key.sign(str(stake).encode())
    stake_dict = stake.to_dict()
    stake_dict["sign"] = base64.b64encode(sign).decode()
    return {"id": "ann-" + stake.id, "type": "stake_announcement", "stake": stake_dict}, sign


def _deliver(peer, pkt):
    async def go():
        await peer.handle_messages(None, pkt)
        await asyncio.sleep(0)  # let the fire-and-forget emit_event task finish

    original = p2p_module.Chain.instance
    p2p_module.Chain.instance = _Chain
    try:
        asyncio.run(go())
    finally:
        p2p_module.Chain.instance = original


def test_received_stake_keeps_its_signature():
    staker = Wallet()
    peer = _receiver()
    pkt, sign = _announcement(staker, 25)

    _deliver(peer, pkt)

    assert peer.current_stakers == {staker.public_key_pem: 25}
    (stake,) = peer.current_stakes
    assert stake.sign == sign


def test_received_stake_survives_the_block_round_trip():
    """What the leader mints must list every stake it knows, not only its own."""
    staker = Wallet()
    peer = _receiver()
    pkt, _ = _announcement(staker, 25)
    _deliver(peer, pkt)

    block = Block("prev", [])
    block.stakers = list(peer.current_stakes)
    parsed = peer.block_dict_to_block(block.to_dict_with_stakers())

    assert [(s.staker, s.amt) for s in parsed.stakers] == [(staker.public_key_pem, 25)]
