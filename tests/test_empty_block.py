from types import SimpleNamespace

from consensus.pos.p2p import Peer


def _block_dict(transactions):
    return {"id": "b1", "prevHash": "abc", "ts": 1700000000000, "transactions": transactions, "stakers": []}


def test_empty_block_is_parsed_not_dropped():
    # PoS mints empty blocks each epoch; receivers must accept them or chains fork.
    peer = SimpleNamespace(stake_dict_to_stake=lambda d: None)
    block = Peer.block_dict_to_block(peer, _block_dict([]))
    assert block is not None
    assert block.transactions == []


def test_block_missing_id_is_still_rejected():
    peer = SimpleNamespace(stake_dict_to_stake=lambda d: None)
    bad = _block_dict([])
    bad["id"] = None
    assert Peer.block_dict_to_block(peer, bad) is None
