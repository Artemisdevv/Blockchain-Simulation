"""
Attack Lab partition must cut every link to the isolated peers.

A socket used to be tied to a peer key only when the other side sent
`peer_info`. Sockets this node dialed itself (outbound) never got one, so the
partition neither closed them nor filtered them: the isolated peers kept
talking to us over those links and the network stayed fully in sync.
"""
import asyncio
import json

from consensus.pos import p2p as p2p_module
from consensus.pos.p2p import Peer, normalize_endpoint

BLOCKED_KEY = "blocked-pem"
OTHER_KEY = "other-pem"


class _Socket:
    def __init__(self, remote):
        self.remote_address = remote
        self.sent = []
        self.closed_with = None

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def close(self, code=1000, reason=""):
        self.closed_with = code

    async def wait_closed(self):
        pass


def _peer():
    peer = Peer.__new__(Peer)
    peer.host, peer.port = "127.0.0.1", 9100
    peer.attack_blocked_peer_keys = set()
    peer.connection_peer_keys = {}
    peer.network_latency_ms = 0
    peer.event_subscribers = set()
    peer.seen_message_ids = set()
    peer.server_connections = set()
    peer.client_connections = set()
    peer.outbound_peers = set()
    peer.got_pong = {}
    peer.have_sent_peer_info = {}
    blocked_ep = normalize_endpoint(("127.0.0.1", 9110))
    other_ep = normalize_endpoint(("127.0.0.1", 9120))
    peer.known_peers = {blocked_ep: ("aswin", BLOCKED_KEY), other_ep: ("shreyas", OTHER_KEY)}
    peer.outbound_peers = {blocked_ep, other_ep}
    return peer, blocked_ep, other_ep


def _dialed(peer, port):
    ws = _Socket(("127.0.0.1", port))
    peer.client_connections.add(ws)  # no connection_peer_keys entry: we dialed it
    return ws


def test_partition_closes_outbound_links_to_isolated_peers():
    peer, *_ = _peer()
    blocked, other = _dialed(peer, 9110), _dialed(peer, 9120)

    asyncio.run(peer.set_attack_partition({BLOCKED_KEY}))

    assert blocked.closed_with == 4003
    assert other.closed_with is None


def test_broadcast_skips_outbound_links_to_isolated_peers():
    peer, *_ = _peer()
    blocked, other = _dialed(peer, 9110), _dialed(peer, 9120)
    peer.attack_blocked_peer_keys = {BLOCKED_KEY}

    asyncio.run(peer.broadcast_message({"type": "x", "id": "1"}))

    assert blocked.sent == []
    assert len(other.sent) == 1


def test_messages_from_isolated_peers_over_outbound_links_are_dropped():
    peer, *_ = _peer()
    blocked = _dialed(peer, 9110)
    peer.attack_blocked_peer_keys = {BLOCKED_KEY}

    asyncio.run(peer.handle_messages(blocked, {"type": "ping", "id": "p1"}))

    assert blocked.sent == [], "a blocked peer's ping must not even be answered"


def test_no_new_outbound_connection_to_an_isolated_peer(monkeypatch):
    dialed = []

    async def fake_connect(uri):
        dialed.append(uri)
        raise OSError("not a real network")

    monkeypatch.setattr(p2p_module.websockets, "connect", fake_connect)
    peer, blocked_ep, other_ep = _peer()
    peer.outbound_peers.clear()
    peer.attack_blocked_peer_keys = {BLOCKED_KEY}

    asyncio.run(peer.connect_to_peer(*blocked_ep))
    assert dialed == []

    asyncio.run(peer.connect_to_peer(*other_ep))  # control: a non-isolated peer is still dialed
    assert len(dialed) == 1


def test_equal_height_fork_resolves_to_the_heavier_chain(monkeypatch):
    """After a partition both sides have the same height; the heavier chain must still win."""
    from tests.test_double_sign_fork_recovery import _install, _packet, _signed_block
    from consensus.pos.blockchain_structures import Wallet

    minority, majority = Wallet(), Wallet()
    genesis = _signed_block(None, minority)
    ours = _signed_block(genesis.hash, minority, stake_amt=5, staker=minority)
    theirs = _signed_block(genesis.hash, majority, stake_amt=40, staker=majority)
    local = _install(monkeypatch, [genesis, ours])
    peer = Peer.__new__(Peer)
    peer.seen_message_ids = set()
    peer.mem_pool, peer.file_hashes = [], {}
    peer.mem_pool_lock, peer.file_hashes_lock = asyncio.Lock(), asyncio.Lock()
    peer.activate_disk_save = "n"
    peer.server_connections, peer.client_connections, peer.event_subscribers = set(), set(), set()
    peer.chain = local

    asyncio.run(peer.handle_messages(None, _packet([genesis, theirs])))

    assert [b.hash for b in local.chain] == [genesis.hash, theirs.hash]
