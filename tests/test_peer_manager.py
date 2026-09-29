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
