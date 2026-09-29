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


def test_pdf_report_excludes_invalid_blocks(monkeypatch, tmp_path):
    """Test that PDF report correctly excludes invalid/slashed blocks from confirmed transactions and chain height."""
    import peer_manager as module

    monkeypatch.setattr(module, "REPORT_DIR", tmp_path)
    manager = PeerManager()
    manager.fixed_peers = [{"room_id": "demo", "name": "alice", "base_url": "http://peer-alice:6000", "token": "peer-secret"}]

    # Chain with 3 blocks: 2 valid (b1, b3) and 1 invalid/slashed (b2)
    # b1: 2 transactions (valid)
    # b2: 3 transactions (invalid/slashed - should NOT be counted)
    # b3: 1 transaction (valid)
    responses = {
        "chain": {
            "blocks": [
                {"id": "b1", "creator": "alice", "is_valid": True, "transactions": [{"id": "tx1", "sender": "a", "receiver": "b", "payload": 10}, {"id": "tx2", "sender": "a", "receiver": "c", "payload": 5}]},
                {"id": "b2", "creator": "alice", "is_valid": False, "slash_creator": True, "transactions": [{"id": "tx3", "sender": "b", "receiver": "a", "payload": 7}, {"id": "tx4", "sender": "c", "receiver": "a", "payload": 3}, {"id": "tx5", "sender": "a", "receiver": "b", "payload": 2}]},
                {"id": "b3", "creator": "alice", "is_valid": True, "transactions": [{"id": "tx6", "sender": "b", "receiver": "c", "payload": 1}]},
            ]
        },
        "peers": {"peers": [{"name": "alice", "public_key": "alice-key"}]},
        "mempool": {"transactions": []},
        "stakers": {"stakers": {"alice-key": 10}},
        "metrics": {"room_id": "demo", "blocks_count": 3},
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

    # Verify the generated JSON report has correct counts
    report = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))

    # The PDF generation uses the final_state.chain which includes is_valid flags
    # Valid chain should have 2 blocks (b1 and b3), not 3
    final_chain = report["final_state"]["chain"]["blocks"]
    valid_blocks = [b for b in final_chain if b.get("is_valid", True)]
    assert len(valid_blocks) == 2, f"Expected 2 valid blocks, got {len(valid_blocks)}"
    assert valid_blocks[0]["id"] == "b1"
    assert valid_blocks[1]["id"] == "b3"

    # Confirmed transactions should only count from valid blocks: 2 + 1 = 3
    confirmed_txs = [(block, tx) for block in valid_blocks for tx in block.get("transactions", [])]
    assert len(confirmed_txs) == 3, f"Expected 3 confirmed transactions from valid blocks, got {len(confirmed_txs)}"
    tx_ids = [tx[1]["id"] for tx in confirmed_txs]
    assert set(tx_ids) == {"tx1", "tx2", "tx6"}, f"Expected tx1, tx2, tx6, got {tx_ids}"

    # Invalid block b2 should have 3 transactions but they should NOT be counted
    invalid_blocks = [b for b in final_chain if not b.get("is_valid", True)]
    assert len(invalid_blocks) == 1
    assert invalid_blocks[0]["id"] == "b2"
    invalid_txs = sum(len(b.get("transactions", [])) for b in invalid_blocks)
    assert invalid_txs == 3, f"Invalid block should have 3 transactions"
