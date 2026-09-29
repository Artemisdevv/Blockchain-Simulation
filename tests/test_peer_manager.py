import pytest

from peer_manager import ManagedPeer, PeerManager, create_app


class FakeProcess:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


class FakeResponse:
    ok = True


def test_manager_uses_start_peer_room_environment():
    created = []

    def factory(command, **kwargs):
        process = FakeProcess(command, **kwargs)
        created.append(process)
        return process

    manager = PeerManager(process_factory=factory, request_get=lambda *args, **kwargs: FakeResponse())
    peer = manager.start_peer("web-node", "team-room")

    assert created[0].args[0][-1].endswith("start_peer.py")
    assert created[0].kwargs["env"]["ACTION"] == "room"
    assert created[0].kwargs["env"]["ROOM_ID"] == "team-room"
    assert created[0].kwargs["env"]["CONSENSUS"] == "pos"
    assert created[0].kwargs["env"]["PEER_NAME"] == "web-node"
    assert created[0].kwargs["env"]["INTERACTIVE"] == "false"
    assert peer.port == 5100


def test_manager_rejects_invalid_settings_before_starting_process():
    manager = PeerManager(process_factory=lambda *args, **kwargs: pytest.fail("must not launch"))

    with pytest.raises(ValueError, match="Node name"):
        manager.start_peer("", "team-room")
    with pytest.raises(ValueError, match="Room ID"):
        manager.start_peer("web-node", "bad room")


def test_create_endpoint_returns_runtime_config_for_pos_peer():
    peer = ManagedPeer("abc123", "web-node", "team-room", 5100, "secret", FakeProcess())

    class StubManager:
        def start_peer(self, *args):
            return peer

    client = create_app(StubManager())[0].test_client()
    response = client.post("/peers", json={"name": "web-node", "room_id": "team-room"})

    assert response.status_code == 201
    assert response.json["peer_id"] == "abc123"
    assert response.json["token"] == "secret"


def _manager():
    return PeerManager(process_factory=FakeProcess, request_get=lambda *a, **k: FakeResponse())


def test_stop_peer_frees_slot_and_port_for_reuse():
    manager = _manager()
    first = manager.start_peer("a", "room")
    manager.stop_peer(first.peer_id)

    assert first.process.returncode == 0
    assert manager.get_peer(first.peer_id) is None
    assert manager.start_peer("b", "room").port == first.port


def test_manager_capacity_recovers_after_disconnects(monkeypatch):
    monkeypatch.setattr("peer_manager.MAX_PEERS", 2)
    manager = _manager()
    a = manager.start_peer("a", "room")
    manager.start_peer("b", "room")
    with pytest.raises(RuntimeError, match="full"):
        manager.start_peer("c", "room")
    manager.stop_peer(a.peer_id)
    manager.start_peer("c", "room")


def test_idle_peer_is_reaped(monkeypatch):
    monkeypatch.setattr("peer_manager.IDLE_TIMEOUT", 0)
    manager = _manager()
    peer = manager.start_peer("a", "room")
    manager.start_peer("b", "room")

    assert peer.process.returncode == 0
    assert peer.peer_id not in manager.peers


def test_delete_endpoint_needs_a_token_from_the_same_room():
    manager = _manager()
    a = manager.start_peer("a", "room-1")
    b = manager.start_peer("b", "room-1")
    outsider = manager.start_peer("c", "room-2")
    client = create_app(manager)[0].test_client()
    auth = lambda peer: {"Authorization": f"Bearer {peer.token}"}

    assert client.delete(f"/peers/{a.peer_id}").status_code == 403
    assert client.delete(f"/peers/{a.peer_id}", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.delete(f"/peers/{a.peer_id}", headers=auth(outsider)).status_code == 403
    assert a.process.returncode is None

    # A room-mate can stop it (Attack Lab), and a node can stop itself (disconnect).
    assert client.delete(f"/peers/{a.peer_id}", headers=auth(b)).status_code == 200
    assert a.process.returncode == 0
    assert client.delete(f"/peers/{b.peer_id}", headers=auth(b)).status_code == 200
    assert client.delete(f"/peers/{b.peer_id}", headers=auth(b)).status_code == 404
