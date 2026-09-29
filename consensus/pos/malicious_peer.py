"""
A PoS peer that double-signs when it wins the leader election.

Unlike the legacy consensus/pos/mal_node.py (a stale copy of the whole Peer with no
web API), this subclasses the current Peer and only overrides block creation, so it
gets every honest feature for free: signalling, the web API, auto-stake, the
Attack Lab hooks. That is what lets the peer manager start it as a *role*.

Attack: when elected, mint two conflicting blocks on the same parent (each pays 75% /
50% of the node's balance to a different peer) and send one to half of its
connections and the other to the rest. Honest nodes each accept one, the chain forks,
and when chains are exchanged the same creator shows up behind two different blocks
at one height, which triggers slashing.
"""
import asyncio
import base64
import json
import uuid
from datetime import datetime

from consensus.pos.blockchain_structures import Block, Chain, Transaction, elect_leader
from consensus.pos.p2p import Peer


class MaliciousPeer(Peer):
    malicious = True

    def __init__(self, host, port, name, activate_disk_load, activate_disk_save):
        super().__init__(host, port, name, True, activate_disk_load, activate_disk_save)

    def _attack_targets(self):
        me = self.wallet.public_key_pem
        return [pk for pk in self.name_to_public_key_dict.values() if pk != me]

    async def create_blocks(self, time):
        if not self.staker:
            return
        await asyncio.sleep(time)

        me = self.wallet.public_key_pem
        seed = Chain.instance.epoch_seed()
        targets = self._attack_targets()
        balance = Chain.instance.calc_balance(me, self.mem_pool, list(self.current_stakes))
        elected = bool(self.current_stakers) and elect_leader(seed, self.current_stakers) == me
        if not elected or not targets or balance <= 0:
            if elected:
                print(f"Elected but not attacking (known targets={len(targets)}, balance={balance})")
            # Nothing to attack with (or not our turn): behave like an honest node,
            # including the losing-the-election cleanup.
            return await super().create_blocks(0)

        await self._double_sign(seed, targets, balance)

    async def _double_sign(self, seed, targets, balance):
        me = self.wallet.public_key_pem
        pending = [tx for tx in self.mem_pool if not Chain.instance.transaction_exists_in_chain(tx)]

        async with self.curr_stakers_condition:
            if elect_leader(seed, self.current_stakers) != me:
                return
            print("\nYou won - double-signing\n")
            vrf_proof = self.wallet.private_key.sign(seed.encode())
            first = targets[0]
            second = targets[1] if len(targets) > 1 else targets[0]

            blocks = []
            for receiver, share in ((first, 0.75), (second, 0.5)):
                tx = Transaction(balance * share, me, receiver)
                tx.sign = self.wallet.private_key.sign(str(tx).encode())
                block = Block(Chain.instance.lastBlock.hash, pending + [tx])
                block.files = self.file_hashes.copy()
                block.seed = seed
                block.vrf_proof = vrf_proof
                block.staked_amt = self.staked_amt
                block.creator = me
                block.stakers = list(self.current_stakes)
                blocks.append(block)

            Chain.instance.chain.append(blocks[0])
            self.last_epoch_end_ts = datetime.now()
            self.staked_amt = 0
            self.current_stakers.clear()
            self.current_stakes.clear()

            packets = []
            for block in blocks:
                block.sign = self.wallet.private_key.sign(str(block).encode())
                pkt = {
                    "type": "new_block",
                    "id": str(uuid.uuid4()),
                    "block": block.to_dict_with_stakers(),
                    "vrf_proof": base64.b64encode(vrf_proof).decode(),
                    "sign": base64.b64encode(block.sign).decode(),
                }
                self.seen_message_ids.add(pkt["id"])
                packets.append(pkt)

            asyncio.create_task(self.emit_event({"type": "block_appended", "block": blocks[0].to_dict_with_stakers()}))
            if self.activate_disk_save == "y":
                self.save_chain_to_disk()

            connections = list(self.server_connections | self.client_connections)
            half = max(1, len(connections) // 2)
            for index, ws in enumerate(connections):
                pkt = packets[0] if index < half else packets[1]
                try:
                    await ws.send(json.dumps(pkt))
                except Exception as e:
                    print(f"Error broadcasting: {e}")
                    self.server_connections.discard(ws)
                    self.client_connections.discard(ws)
            # With a single victim it only ever sees the first block; send the second
            # too so the evidence of the conflicting pair exists on the network.
            if len(connections) == 1:
                try:
                    await connections[0].send(json.dumps(packets[1]))
                except Exception as e:
                    print(f"Error broadcasting: {e}")

        self.last_epoch_end_ts = datetime.now()
