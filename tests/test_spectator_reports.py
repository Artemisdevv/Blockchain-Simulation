import json

from peer_manager import PeerManager, create_app


class UpstreamResponse:
    ok = True
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, data):
        self.data = data
        self.content = json.dumps(data).encode()

    def json(self):
        return self.data


def test_spectator_link_scopes_read_only_room_access(monkeypatch, tmp_path):
    import peer_manager as module

    monkeypatch.setattr(module, "REPORT_DIR", tmp_path)
    manager = PeerManager()
    manager.fixed_peers = [{"room_id": "demo", "name": "alice", "base_url": "http://peer-alice:6000", "token": "peer-secret"}]
    monkeypatch.setattr(module.requests, "get", lambda url, **kwargs: UpstreamResponse({"blocks": []}))
    client = create_app(manager)[0].test_client()

    assert client.post("/spectator-links", json={"room_id": "demo"}).status_code == 403
    assert client.post("/spectator-links", json={"room_id": "demo"}, headers={"Authorization": "Bearer nope"}).status_code == 403
    issued = client.post("/spectator-links", headers={"Authorization": "Bearer peer-secret"})
    assert issued.status_code == 200
    assert issued.json["room_id"] == "demo"
    assert manager.issuer_token not in issued.get_data(as_text=True)
    token = issued.json["spectator_token"]

    read = client.get(f"/spectator/{token}/chain", headers={"Authorization": f"Bearer {token}"})
    assert read.status_code == 200
    mutation = client.post(f"/spectator/{token}/transactions", json={}, headers={"Authorization": f"Bearer {token}"})
    assert mutation.status_code == 403
    attack_mutation = client.post(f"/spectator/{token}/attack-lab/partition", json={"peer_keys": ["peer"]}, headers={"Authorization": f"Bearer {token}"})
    assert attack_mutation.status_code == 403
    malicious_trigger = client.post(f"/spectator/{token}/malicious/trigger", json={}, headers={"Authorization": f"Bearer {token}"})
    assert malicious_trigger.status_code == 403
    # A body room_id is ignored: the link always targets the caller's own room.
    other = client.post("/spectator-links", json={"room_id": "elsewhere"}, headers={"Authorization": "Bearer peer-secret"})
    assert other.json["room_id"] == "demo"


def test_spectator_pdf_report_is_generated_from_structured_report(monkeypatch, tmp_path):
    import peer_manager as module

    monkeypatch.setattr(module, "REPORT_DIR", tmp_path)
    manager = PeerManager()
    manager.fixed_peers = [{"room_id": "demo", "name": "alice", "base_url": "http://peer-alice:6000", "token": "peer-secret"}]
    responses = {
        "chain": {"blocks": [{"id": "b1", "creator": "alice", "transactions": []}]},
        "peers": {"peers": [{"name": "alice", "public_key": "alice-key"}]},
        "mempool": {"transactions": []},
        "stakers": {"stakers": {"alice-key": 10}},
        "metrics": {"room_id": "demo", "blocks_count": 1},
        "invariants": {"honest_consensus": True},
        "attack-lab/state": {"blocked_peers": [], "latency_ms": 0, "censored_receivers": []},
    }
    monkeypatch.setattr(module.requests, "get", lambda url, **kwargs: UpstreamResponse(next(value for key, value in responses.items() if url.endswith("/" + key))))
    client = create_app(manager)[0].test_client()
    token = manager.make_spectator_token("demo")

    response = client.get(f"/spectator/{token}/report.pdf", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")
    report = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert report["run"]["room_id"] == "demo"
    assert report["final_state"]["completeness"]["mempool"] == "observed snapshot only"
    restored = PeerManager()
    assert restored.get_run("demo").run_id == report["run"]["run_id"]
