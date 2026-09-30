"""The dashboard shows the room the node joined, not a hard-coded "demo"."""
import asyncio
from types import SimpleNamespace

from consensus.pos import p2p as p2p_mod
from start_peer import run_peer
from webapi.rate_limit import FailedAuthTracker, RateLimiter
from webapi.server import create_app

TOKEN = "t"


class _Peer(SimpleNamespace):
    async def start(self, *args, **kwargs):
        pass


def test_run_peer_records_the_room_id_on_the_peer():
    peer = _Peer()
    asyncio.run(run_peer(peer, "create", None, None, None, None, "team-room", False, 0, interactive=False))
    assert peer.room_id == "team-room"


def test_metrics_report_the_peers_room(monkeypatch):
    monkeypatch.setattr(p2p_mod.Chain, "instance", None)
    peer = SimpleNamespace(
        known_peers={}, name_to_public_key_dict={}, mem_pool=[], staker=True, auto_stake=False,
        wallet=SimpleNamespace(public_key_pem="pem"), room_id="team-room",
    )
    app = create_app(peer, loop=None, token=TOKEN, limiter=RateLimiter(1000, 60), auth_tracker=FailedAuthTracker())
    body = app.test_client().get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).get_json()
    assert body["room_id"] == "team-room"
