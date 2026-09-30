"""
A node on a different branch asks for chains as soon as it sees a block that
does not build on its tip, instead of waiting for the 60s periodic exchange,
and tells browsers when it actually switches chains.
"""
import asyncio
import base64
import json

from consensus.pos import p2p as p2p_module
from consensus.pos.blockchain_structures import Block, Chain, Wallet
from consensus.pos.p2p import Peer
from tests.test_double_sign_fork_recovery import _fork_fixture, _install, _packet, _peer


class _Socket:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def _wired_peer(local_chain):
    peer = _peer(local_chain)
    peer.network_latency_ms = 0
    peer.p2p_socket = _Socket()
    peer.client_connections = {peer.p2p_socket}
    peer.browser = _Socket()
    peer.event_subscribers = {peer.browser}
    return peer


def _drain(coro):
    async def go():
        result = await coro
        await asyncio.sleep(0)
        await asyncio.sleep(0)  # fire-and-forget emit_event tasks
        return result

    return asyncio.run(go())


def _types(sock):
    return [m["type"] for m in sock.sent]


class _FakeChain:
    def __init__(self, tip):
        self.chain = [tip, tip]
        self.lastBlock = tip

    def isValidBlock(self, block):
        return False


def _foreign_block_packet(wallet):
    block = Block("hash-of-a-block-we-do-not-have", [])
    block.creator = wallet.public_key_pem
    sign = wallet.private_key.sign(str(block).encode())
    return {
        "id": "blk-1",
        "type": "new_block",
        "block": block.to_dict_with_stakers(),
        "vrf_proof": base64.b64encode(b"x").decode(),
        "sign": base64.b64encode(sign).decode(),
    }


def test_block_that_does_not_fit_the_tip_requests_chains_once(monkeypatch):
    wallet = Wallet()
    tip = Block("parent", [])
    tip.creator = wallet.public_key_pem
    monkeypatch.setattr(p2p_module.Chain, "instance", _FakeChain(tip))
    peer = _wired_peer(None)

    _drain(peer.handle_messages(None, _foreign_block_packet(wallet)))
    second = _foreign_block_packet(wallet)
    second["id"] = "blk-2"
    _drain(peer.handle_messages(None, second))

    assert _types(peer.p2p_socket) == ["chain_request"], "rate-limited to one request in the interval"
    assert _types(peer.browser) == ["resync_started"]


def test_chain_replaced_event_only_when_the_chain_actually_switches(monkeypatch):
    genesis, on_a, on_b, ahead = _fork_fixture()
    local = _install(monkeypatch, [genesis, on_b])
    peer = _wired_peer(local)

    _drain(peer.handle_messages(None, _packet([genesis, on_a, ahead])))

    events = [m for m in peer.browser.sent if m["type"] == "chain_replaced"]
    assert events == [{"type": "chain_replaced", "old_length": 2, "new_length": 3}]

    # Same chain again (fresh message id): nothing changes, nothing is announced.
    peer.browser.sent.clear()
    packet = _packet([genesis, on_a, ahead])
    packet["id"] = "chain-2"
    _drain(peer.handle_messages(None, packet))
    assert peer.browser.sent == []
