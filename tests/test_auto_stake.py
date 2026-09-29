import asyncio
from types import SimpleNamespace

import pytest

from consensus.pos import p2p
from consensus.pos.p2p import Peer


class _Chain:
    balance = 0

    @staticmethod
    def calc_balance(*_args):
        return _Chain.balance


def _run_loop(peer, seconds=0.05):
    async def go():
        task = asyncio.create_task(Peer.auto_stake_loop(peer, poll_seconds=0.01))
        await asyncio.sleep(seconds)
        task.cancel()

    asyncio.run(go())


def _peer(staked_amt=0, auto_stake=True):
    calls = []

    async def stake_coin(amt):
        calls.append(amt)
        return {"ok": True}

    peer = SimpleNamespace(
        staked_amt=staked_amt,
        auto_stake=auto_stake,
        wallet=SimpleNamespace(public_key_pem="pk"),
        mem_pool=[],
        current_stakes={},
        stake_coin=stake_coin,
    )
    return peer, calls


@pytest.fixture(autouse=True)
def _chain(monkeypatch):
    monkeypatch.setattr(p2p.Chain, "instance", _Chain, raising=False)


def test_stakes_half_of_balance():
    _Chain.balance = 50
    peer, calls = _peer()
    _run_loop(peer)
    assert calls and calls[0] == 25


def test_skips_when_no_balance_or_already_staked():
    _Chain.balance = 0
    peer, calls = _peer()
    _run_loop(peer)
    assert calls == []
    _Chain.balance = 50
    peer, calls = _peer(staked_amt=10)
    _run_loop(peer)
    assert calls == []


def test_does_nothing_when_toggle_off():
    _Chain.balance = 50
    peer, calls = _peer(auto_stake=False)
    _run_loop(peer)
    assert calls == []
