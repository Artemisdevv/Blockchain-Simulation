"""
Regression test for issue #13: calc_balance awarded the +6 miner reward to
the genesis block itself (since its creator field equals the node's own
pubkey), so a fresh single-node network started at 56 coins instead of 50.
"""
from consensus.pos.blockchain_structures import Transaction, Chain, Wallet


def test_genesis_balance_is_exactly_50_no_miner_reward():
    Chain.instance = None
    wallet = Wallet()
    chain = Chain(publicKey=wallet.public_key_pem, privatekey=wallet.private_key)

    balance = chain.calc_balance(wallet.public_key_pem, pending_transactions=[], current_stakes=[])
    assert balance == 50, f"expected 50 (genesis grant only), got {balance}"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
