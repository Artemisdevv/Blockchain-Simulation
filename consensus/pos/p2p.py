import asyncio, websockets, traceback, hashlib
import argparse, json, uuid, base64
import threading, socket, os, subprocess
from datetime import datetime, timedelta
from typing import Set, Dict, List, Tuple, Any
from consensus.pos.blockchain_structures import Transaction, Stake, Block, Wallet, Chain, isvalidChain, weight_of_chain, elect_leader
from shared_blockchain_structures import FAUCET_VERIFYING_KEY
from ipfs.ipfs import addToIpfs, download_ipfs_file_subprocess
from smart_contract.contracts_db import SmartContractDatabase
from smart_contract.secure_executor import SecureContractExecutor
from storage.storage_manager import save_key, load_key, save_chain, load_chain, save_peers, load_peers
from ecdsa import VerifyingKey, BadSignatureError
import tempfile
from pathlib import Path
import ast

MAX_CONNECTIONS = 8
MAX_OUTPUT=2**256
EPOCH_TIME=60
AUTO_STAKE_SETTLE_SECONDS=5
GAS_PRICE = 0.001 # coin per gas unit
BASE_DEPLOY_COST = 5
CONSENSUS ="pos"

class VrfThresholdException(Exception):
    pass

def get_random_element(s):
    """
        Return a random element from a set
    """
    import random
    return random.choice(list(s)) if s else None

def normalize_endpoint(ep):
    """
        Return host resolved into ipv4 address and port converted into int datatype - maintains consistency in the code
    """
    host, port = ep
    return (socket.gethostbyname(host), int(port))

def get_contract_code_from_notepad():
    # Create a temporary file with a .py extension
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w+', encoding='utf-8') as tmp_file:
        temp_filename = tmp_file.name
        tmp_file.write("# Write your smart contract function here.\n")
        tmp_file.write("def contract_logic(parameter1, parameter2, parameter3, state):\n")
        tmp_file.write("    # your code here\n")
        tmp_file.write("    return state, 'some message'\n")
    
    # Open it in Notepad (waits until closed)
    subprocess.call(["notepad.exe", temp_filename])

    # Read the edited code
    with open(temp_filename, 'r', encoding='utf-8') as f:
        contract_code = f.read()

    # Optional: remove the temp file
    os.remove(temp_filename)

    return contract_code

class Peer:
    def __init__(self, host, port, name, staker:bool, activate_disk_load, activate_disk_save):
        self.host = host
        self.name = name
        self.staker=staker
        self.auto_faucet_tx_id=None # id of the one-time faucet request auto_stake_loop made
        self.auto_stake=False # toggled via webapi /auto_stake; see auto_stake_loop

        self.activate_disk_save = activate_disk_save

        self.port = port
        self.ipfs_port = port + 50  # API port
        self.gateway_port = port + 81  # Gateway port
        self.swarm_tcp = port + 2
        self.swarm_udp = port + 3
        self.repo_path = Path.home() / f".ipfs_{port}"
        self.env = os.environ.copy()
        self.env["IPFS_PATH"] = str(self.repo_path)

        self.server_connections :Set[websockets.WebSocketServerProtocol]=set() # For inbound peers ie websockets that connect to us and treat us as the server
        self.client_connections :Set[websockets.WebSocketServerProtocol]=set() # For outbound peers ie websockets we initiated, we are the clients
        self.attack_blocked_peer_keys: Set[str] = set()
        self.connection_peer_keys: Dict[websockets.WebSocketServerProtocol, str] = {}
        self.network_latency_ms = 0
        self.censored_receivers: Set[str] = set()

        self.outbound_peers: Set[tuple]=set()
        # The peers to which we currently maintain a outbound connection

        self.seen_message_ids: Set[str]= set()
        # Used to remove duplicate messages, messages that return to us after a round of broadcasting

        self.event_subscribers: Set[websockets.WebSocketServerProtocol] = set()
        # Browser clients connected to the /events websocket (webapi/events.py)

        if activate_disk_load == "y":
            self.load_known_peers_from_disk()
        else:
            self.known_peers = None
        if not self.known_peers:
            self.known_peers : Dict[Tuple[str, int], Tuple[str, str]]={} # (host, port):(name, public key)
        """
            We store all the peers we know here, we compare this with outbound peers in dicover_peers
            to find to which nodes we have not yet made a connection
        """
        
        self.staked_amt:int=0
        self.got_pong: Dict[websockets.WebSocketServerProtocol, bool]={}
        """
            We set the value of each websocket in this dictionary false before sending ping
            If we get a pong from a particular websocekt we assign it True.
            We remove all websockets that don't send a pong in time. 
        """

        self.have_sent_peer_info: Dict[websockets.WebSocketServerProtocol, bool]={}
        """
            When we form an outbound connection, on receiving the first pong after our first ping
            we send them our peer_info, but we don't want to keep making the elaborate handshake
            so after the first time of getting pong we don't send them our peer info
            I'll explain the handshake in README.md
        """

        
        self.last_epoch_end_ts=datetime.now()
        self.mem_pool: List[Transaction]=list()
        self.mem_pool_lock=asyncio.Lock() 
        
        self.file_hashes: Dict[str, str]={}
        self.file_hashes_lock=asyncio.Lock()
        self.daemon_process=None

        self.current_stakes: set[Stake]=set() # Public key is stored as pem string
        self.current_stakers:Dict[str, int]={}
        self.curr_stakers_condition=asyncio.Condition() 
        
        self.name_to_public_key_dict: Dict[str, str]={}
        
        if activate_disk_load == "y":
            self.load_key_from_disk()
        else:
            self.wallet = None
        if not self.wallet:
            self.wallet=Wallet()
            if self.activate_disk_save == "y":
                self.save_key_to_disk()
        
        if activate_disk_load == "y":
            self.load_chain_from_disk() # If no chain data stored, self.chain will be assigned to None
        else:
            self.chain = None

        self.contractsDB = SmartContractDatabase()

        self.create_block_condition=asyncio.Condition()
        """
            Starts a timer for the creation of next block
        """
        self.mine_task=None

    def save_key_to_disk(self):
        key = self.wallet.private_key_pem
        save_key(key, CONSENSUS)

    def load_key_from_disk(self):
        key = load_key(CONSENSUS)
        if not key:
            self.wallet = None
            return
        self.wallet = Wallet(key)

    def load_chain_from_disk(self):
        block_dict_list = load_chain(CONSENSUS)
        if not block_dict_list:
            self.chain = None
            return
        block_list: List[Block]=[]

        for block_dict in block_dict_list:
            block=self.block_dict_to_block(block_dict)
            block_list.append(block)

        self.chain=Chain(blockList=block_list)

    def save_chain_to_disk(self):
        chain = Chain.instance.to_block_dict_list()
        save_chain(chain, CONSENSUS)

    def save_known_peers_to_disk(self):
        content = {}
        for key, value in self.known_peers.items():
            content[json.dumps(key)] = list(value)
        save_peers(content, CONSENSUS)

    def load_known_peers_from_disk(self):
        content = load_peers(CONSENSUS)
        if not content:
            self.known_peers = None
            return
        self.known_peers = {}
        for key, value in content.items():
            self.known_peers[tuple(ast.literal_eval(key))] = tuple(value)
        for key, value in self.known_peers:
            self.name_to_public_key_dict[value[0].lower()] = value[1]

    async def send_peer_info(self, websocket):
        """
            Function made to send the peer (self) info
        """
        pkt={
            "type":"peer_info",
            "id":str(uuid.uuid4()),
            "data":{
                "host":self.host,
                "port":self.port,
                "name":self.name,
                "public_key":self.wallet.public_key_pem
                }
        }

        self.seen_message_ids.add(pkt["id"])
        await websocket.send(json.dumps(pkt))

    async def send_known_peers(self, websocket):
        """
            Function for sending known_peers
            (information regarding all the peers we know)
        """
        peers=[{"host":h, "port":p, "name":n, "public_key":s}
               for (h, p), (n,s) in self.known_peers.items()]
        peers.append({"host":self.host, "port":self.port, "name":self.name, "public_key":self.wallet.public_key_pem})
        pkt={
            "type":"known_peers",
            "id":str(uuid.uuid4()),
            "peers":peers
        }
        self.seen_message_ids.add(pkt["id"])
        await websocket.send(json.dumps(pkt))

    def block_dict_to_block(self, block_dict:Dict[str, Any]):    
        """
            Verified whether given information in block_dict is valid and
            creates a block out of the information or returns None
            We sent a receive blocks as a dictionary
            block["trasnsactions"] is a list of dictionaries that
            represent transactions
        """

        new_block_id=block_dict.get("id")
        new_block_prevHash=block_dict.get("prevHash")
        new_block_ts=block_dict.get("ts")

        transactions=[]
        for transaction_dict in block_dict["transactions"]:
            transaction=Transaction(transaction_dict["payload"], transaction_dict["sender"], transaction_dict["receiver"], transaction_dict["id"], transaction_dict["ts"])
            # "sign" key is only absent for the genesis block's own unsigned
            # initial grant (see txs_to_json_digestable_form) - a
            # post-genesis Genesis-sender (faucet) transaction is signed by
            # FAUCET_SIGNING_KEY and must be decoded like any other sender.
            if transaction_dict.get("sign"):
                transaction.sign=base64.b64decode(transaction_dict["sign"])
            transactions.append(transaction)
        
        # Genesis block doesn't have prevHash, it's an empty string. A block may
        # legitimately carry zero transactions: create_blocks() mints empty blocks
        # each epoch to rotate stakers, so an empty list must not be rejected.
        if(not(new_block_id and new_block_ts)):
            return None
        
        newBlock=Block(new_block_prevHash, transactions, new_block_ts, new_block_id)   
        staked_amt=block_dict.get("staked_amt")
        if(staked_amt):
            newBlock.staked_amt=staked_amt

        if(block_dict.get("files")):
            newBlock.files=block_dict["files"]

        creator=block_dict.get("creator")
        if(creator):
            newBlock.creator=creator

        sign_b64=block_dict.get("sign")

        if(sign_b64):
            newBlock.sign=base64.b64decode(sign_b64)

        stakers_list:List[Stake]=[]
        for staker_dict in block_dict["stakers"]:
            new_Stake=self.stake_dict_to_stake(staker_dict)
            if(not new_Stake):
                continue
            stakers_list.append(new_Stake)
        
        vrf_proof=block_dict.get("vrf_proof_b64")
        seed=block_dict.get("seed")
        if(vrf_proof and seed):
            newBlock.vrf_proof=base64.b64decode(vrf_proof)
            newBlock.seed=seed

        newBlock.stakers=stakers_list
        return newBlock
    
    def stake_dict_to_stake(self, stake_dict:Dict[str, Any]):    
        """
            This function creates a stake out of the information
            stored inside stake_dict
        """
        id=stake_dict.get("id")
        staker=stake_dict.get("staker")
        amt=stake_dict.get("amt")
        ts=stake_dict.get("ts")
        sign=stake_dict.get("sign")

        if(not(id and staker and amt and sign)):
            return None
        
        stake=Stake(staker, amt, ts)
        stake.id=id

        sign_bytes=base64.b64decode(sign)        
        stake.sign=sign_bytes
        return stake

    def valid_deploy_transaction(self, payload):
        contract_code = payload[0]
        gas_used = len(contract_code)//10 + BASE_DEPLOY_COST
        amount = gas_used * GAS_PRICE
        if amount != payload[-1]:
            return False
        return True

    def valid_invoke_transaction(self, payload):
        contract_id = payload[0]
        func_name = payload[1]
        args = payload[2]
        response = self.run_contract([contract_id, func_name, args])
        if(response["error"] != None):
            return False
        state = response["state"]
        gas_used = response["gas_used"]
        amount = gas_used * GAS_PRICE
        if state != payload[3]:
            return False
        if amount != payload[-1]:
            return False
        return True

    def get_unique_name(self, base_name):
        existing_names = []
        for key, value in self.known_peers.items():
            existing_names.append(value[0].lower())

        existing_names.append(self.name)
        
        base_name = base_name.lower()
        if base_name not in existing_names:
            return base_name
        
        counter = 1
        while True:
            new_name = f"{base_name}{counter}"
            if new_name not in existing_names:
                return new_name
            counter += 1

    async def handle_messages(self, websocket, msg):
        """
            This is a function to handle messages as the name suggests
            It faciliates the handshake between client and server. 
            It also accepts transactions, blocks and chains in the format
            in which we send them. Then this function recreates these and
            performs the necessary operations
        """
        # Read the handshake protocol within readme to understand the flow of messages

        t = msg.get("type")
        id = msg.get("id")
        # Every message has a type and an id

        if not t or not id:
            return
        sender_key = getattr(self, "connection_peer_keys", {}).get(websocket)
        if sender_key in getattr(self, "attack_blocked_peer_keys", set()) and t not in ("peer_info", "add_peer", "new_peer"):
            return
        if id in self.seen_message_ids:
            return
        
        self.seen_message_ids.add(id)

        if t == "ping":
            # print("Received Ping")
            pkt = {
                "type": "pong",
                "id": str(uuid.uuid4())
            }
            self.seen_message_ids.add(pkt["id"])
            await websocket.send(json.dumps(pkt))

        elif t == "pong":
            self.got_pong[websocket] = True
            if not self.have_sent_peer_info.get(websocket, True):
                await self.send_peer_info(websocket)
                self.have_sent_peer_info[websocket] = True

        elif t == 'peer_info':
            data = msg.get("data")
            if not data:
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            self.connection_peer_keys[websocket] = data['public_key']
            if data['public_key'] in self.attack_blocked_peer_keys:
                await websocket.close(code=4003, reason="peer isolated by Attack Lab")
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data['host'], data['port']))
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                self.known_peers[normalized_endpoint] = (data['name'], data['public_key'])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data['name'].lower()] = data['public_key']
                asyncio.create_task(self.emit_event({"type": "peer_discovered", "peer": {"host": data['host'], "port": data['port'], "name": data['name'], "public_key": data['public_key']}}))
                print(f"Registered peer {data['name']} {data['host']}:{data['port']}")
                await self.send_known_peers(websocket)

        elif t == "add_peer":
            data = msg.get("data")
            if not data:
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            self.connection_peer_keys[websocket] = data['public_key']
            if data['public_key'] in self.attack_blocked_peer_keys:
                await websocket.close(code=4003, reason="peer isolated by Attack Lab")
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data["host"], data["port"]))
            new_peer_msg_id = str(uuid.uuid4())
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                proposed_name = self.get_unique_name(data["name"])
                if proposed_name != data["name"]:
                    pkt = {
                        "type": "change_name",
                        "id": str(uuid.uuid4()),
                        "new_peer_msg_id": new_peer_msg_id,
                        "new_name": proposed_name
                    }
                    await websocket.send(json.dumps(pkt))
                    data["name"] = proposed_name
                self.known_peers[normalized_endpoint] = (data["name"], data["public_key"])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data["name"].lower()] = data["public_key"]
                asyncio.create_task(self.emit_event({"type": "peer_discovered", "peer": {"host": data["host"], "port": data["port"], "name": data["name"], "public_key": data["public_key"]}}))
                print(f"Registered peer {data['name']} {data['host']}:{data['port']}")
                await self.send_known_peers(websocket)
                pkt = {
                    "type": "new_peer",
                    "id": new_peer_msg_id,
                    "data": {
                        "host": data["host"],
                        "port": data["port"],
                        "name": data["name"],
                        "public_key": data["public_key"]
                    }
                }
                self.seen_message_ids.add(pkt["id"])
                await self.broadcast_message(pkt)

        elif t == "new_peer":
            data = msg.get("data")
            if not data:
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data["host"], data["port"]))
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                self.known_peers[normalized_endpoint] = (data["name"], data["public_key"])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data["name"].lower()] = data["public_key"]
                asyncio.create_task(self.emit_event({"type": "peer_discovered", "peer": {"host": data["host"], "port": data["port"], "name": data["name"], "public_key": data["public_key"]}}))
                print(f"Registered peer {data['name']} {data['host']}:{data['port']}")
                await self.broadcast_message(msg)

        elif t == "change_name":
            new_name = msg.get("new_name")
            new_peer_msg_id = msg.get("new_peer_msg_id")
            if not new_name or not new_peer_msg_id:
                return
            
            self.name = new_name
            self.seen_message_ids.add(new_peer_msg_id)

        elif t == "known_peers":
            peers = msg.get("peers")
            if not peers:
                return
            
            new_peer_found = False
            for peer in peers:
                if not all(k in peer for k in ['host', 'port', 'name', 'public_key']):
                    continue
                
                normalized_self = normalize_endpoint((self.host, self.port))
                normalized_endpoint = normalize_endpoint((peer['host'], peer['port']))
                if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                    print(f"Discovered peer {peer['name']} at {peer['host']}:{peer['port']}")
                    new_peer_found = True
                    self.known_peers[normalized_endpoint] = (peer['name'], peer['public_key'])
                    self.name_to_public_key_dict[peer['name'].lower()] = peer['public_key']
                    asyncio.create_task(self.emit_event({"type": "peer_discovered", "peer": {"host": peer['host'], "port": peer['port'], "name": peer['name'], "public_key": peer['public_key']}}))
            if new_peer_found:
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
            pkt = {
                "type": "chain_request",
                "id": str(uuid.uuid4())
            }
            await websocket.send(json.dumps(pkt))

        elif t == "file":
            cid = msg.get("cid")
            desc = msg.get("desc")
            if not cid or not desc:
                return
            
            async with self.file_hashes_lock:
                self.file_hashes[cid] = desc

            await self.broadcast_message(msg)

        elif t == "new_tx":
            tx_str = msg.get("transaction")
            sender_pem = msg.get("sender_pem")
            sign = msg.get("sign")

            if not tx_str or not sender_pem:
                return

            try:
                tx = json.loads(tx_str)
            except json.JSONDecodeError:
                return

            if not all(k in tx for k in ['payload', 'sender', 'receiver', 'id', 'ts']):
                return
            if tx['receiver'] in getattr(self, "censored_receivers", set()):
                return

            amount = 0
            if tx['receiver'] == "deploy" or tx['receiver'] == "invoke":
                if not isinstance(tx['payload'], list) or len(tx['payload']) == 0:
                    return
                amount = tx['payload'][-1]
            else:
                amount = tx['payload']

            if amount <= 0:
                print("\nInvalid Transaction, amount<=0\n")
                return

            transaction = Transaction(tx['payload'], tx['sender'], tx['receiver'], tx['id'], tx['ts'])
            if Chain.instance.transaction_exists_in_chain(transaction):
                print(f"{self.name} Transaction already exists in chain")
                return
            if any(t.id == transaction.id for t in self.mem_pool):
                # Network delivery isn't exactly-once (self-loops, multi-path
                # gossip, retries) - the chain-membership check above only
                # catches already-confirmed txs, not ones already sitting in
                # our own mempool. Without this, the same transaction can be
                # appended twice, doubling its counted value everywhere
                # (pending balance, mempool totals) until it's mined.
                print(f"{self.name} Transaction already in mempool")
                return

            if transaction.receiver == "deploy":
                if not self.valid_deploy_transaction(transaction.payload):
                    return
            if transaction.receiver == "invoke":
                if not self.valid_invoke_transaction(transaction.payload):
                    return

            if transaction.sender == "Genesis":
                # "Genesis" is just a string - trusting it alone would let
                # any peer gossip an unlimited fake mint. Real faucet mints
                # are signed by the well-known faucet key
                # (webapi/server.py's /faucet), so verify that instead of
                # the sender field, plus the same amount bound the faucet
                # endpoint itself enforces.
                if amount > 500:
                    print("\nInvalid Genesis mint amount\n")
                    return
                if not sign:
                    print("\nUnsigned Genesis mint rejected\n")
                    return
                try:
                    sign_bytes = base64.b64decode(sign)
                    FAUCET_VERIFYING_KEY.verify(sign_bytes, tx_str.encode())
                except Exception:
                    print("\nForged Genesis mint (bad faucet signature)\n")
                    return
                transaction.sign = sign_bytes
            else:
                if not sign:
                    return
                try:
                    sign_bytes = base64.b64decode(sign)
                except Exception:
                    print("Invalid signature encoding")
                    return

                if amount > Chain.instance.calc_balance(transaction.sender, self.mem_pool, list(self.current_stakes)):
                    print("\nAttempt to spend more than one has, Invalid transaction\n")
                    return

                try:
                    public_key = VerifyingKey.from_pem(sender_pem.encode())
                    public_key.verify(
                        sign_bytes,
                        tx_str.encode()
                    )
                except BadSignatureError as e:
                    print("Invalid Signature")
                    return

                transaction.sign = sign_bytes

            print("\nValid Transaction")
            print(f"\n{msg['type']}: {msg['transaction']}")
            print("\n")

            async with self.mem_pool_lock:
                self.mem_pool.append(transaction)
            await self.broadcast_message(msg)

        elif t == "stake_announcement":
            stake_dict = msg.get("stake")
            if not stake_dict:
                return
            
            if not all(k in stake_dict for k in ["staker", "amt", "ts", "id", "sign"]):
                return
            
            stake = Stake(stake_dict["staker"], stake_dict["amt"], stake_dict["ts"])
            stake.id = stake_dict.get("id")

            pid = stake.staker
            amt = stake.amt

            if pid and amt:
                if amt <= 0:
                    return
                
                try:
                    sign = base64.b64decode(stake_dict["sign"])
                except Exception:
                    print("\nInvalid signature encoding\n")
                    return

                try:
                    vk = VerifyingKey.from_pem(pid)
                    vk.verify(sign, str(stake).encode())
                except BadSignatureError:
                    print("\nWrong signature\n")
                    return

                if stake.amt > Chain.instance.calc_balance(stake.staker, self.mem_pool, list(self.current_stakes)):
                    print("\nInvalid stake, staked more than available\n")
                    return

                async with self.curr_stakers_condition:
                    self.current_stakes.add(stake)
                    self.current_stakers[pid] = int(amt)
                    print(f"New stake : {pid}:{amt}")
                asyncio.create_task(self.emit_event({"type": "stake_registered", "staker": pid, "amount": int(amt)}))
                await self.broadcast_message(msg)

        elif t == "new_block":
            new_block_dict = msg.get("block")
            vrf_proof_str = msg.get("vrf_proof")
            sign_str = msg.get("sign")
            
            if not new_block_dict or not vrf_proof_str or not sign_str:
                return
            
            if "creator" not in new_block_dict:
                return
            
            newBlock = self.block_dict_to_block(new_block_dict)
            if newBlock is None:
                print("\nInvalid Block (malformed)\n")
                return

            if not Chain.instance.isValidBlock(newBlock):
                # A second, different block on the same parent from the creator of our tip
                # is direct double-sign evidence (equivocation): both blocks are signed by
                # the same key, so slash right away instead of waiting for a chain exchange.
                tip = Chain.instance.lastBlock
                if (len(Chain.instance.chain) > 1 and tip.creator and tip.creator == newBlock.creator
                        and tip.prevHash == newBlock.prevHash and not tip.is_equal(newBlock)):
                    try:
                        newBlock.sign = base64.b64decode(sign_str)
                    except Exception:
                        return
                    print("\nConflicting block from the same creator - checking for double-sign\n")
                    await self.verify_and_slash(tip, newBlock, len(Chain.instance.chain) - 1, [])
                    return
                print("\nInvalid Block\n")
                return

            try:
                # Convert Unix timestamp to datetime
                if isinstance(newBlock.ts, (int, float)):
                    block_time = datetime.fromtimestamp((newBlock.ts)/1000)
                elif isinstance(newBlock.ts, str):
                    block_time = datetime.fromisoformat(newBlock.ts)
                elif isinstance(newBlock.ts, datetime):
                    block_time = newBlock.ts
                else:
                    print("\nInvalid Block (unknown timestamp format)\n")
                    return

                current_time = datetime.now()

                # Check block isn't from the future (with tolerance for clock skew)
                if block_time > current_time + timedelta(seconds=10):
                    print("\nInvalid Block (timestamp in future)\n")
                    return

                # Check block isn't too old
                if block_time < current_time - timedelta(seconds=EPOCH_TIME * 2):
                    print("\nInvalid Block (timestamp too old)\n")
                    return

                # Verify minimum time since last block
                if len(Chain.instance.chain) > 0:
                    last_block_ts = Chain.instance.lastBlock.ts
                    # Handle the same types for lastBlock timestamp
                    if isinstance(last_block_ts, (int, float)):
                        last_block_time = datetime.fromtimestamp(last_block_ts/1000)
                    elif isinstance(last_block_ts, str):
                        last_block_time = datetime.fromisoformat(last_block_ts)
                    elif isinstance(last_block_ts, datetime):
                        last_block_time = last_block_ts
                    else:
                        print("\nInvalid Block (cannot validate timing against last block)\n")
                        return
                        
                    time_diff = (block_time - last_block_time).total_seconds()
                    
                    # Blocks shouldn't come faster than the staking registration period
                    if time_diff < EPOCH_TIME * 5/6:
                        print(f"\nInvalid Block (created too quickly: {time_diff}s < {EPOCH_TIME * 5/6}s)\n")
                        return
            except (ValueError, AttributeError, TypeError, OSError) as e:
                print(f"\nInvalid Block (bad timestamp format): {e}\n")
                return
            
            try:
                vk = VerifyingKey.from_pem(new_block_dict["creator"])
                vrf_proof = base64.b64decode(vrf_proof_str)
                sign = base64.b64decode(sign_str)
            except Exception as e:
                print(f"\nInvalid Block (encoding error): {e}\n")
                return

            print(f"\n{new_block_dict}\n")
            try:
                try:
                    vk.verify(vrf_proof, Chain.instance.epoch_seed().encode())
                except BadSignatureError as e:
                    print(f"\nInvalid Block (VRF_PROOF Signature Error) {e}\n")
                    return

                try:
                    vk.verify(sign, str(newBlock).encode())
                except BadSignatureError as e:
                    print(f"\nInvalid Block (Block Signature Error) {e}\n")
                    return
                
                if newBlock.seed != Chain.instance.epoch_seed():
                    print("\nSeed May Have Been Altered\n")
                    return

                newBlock.sign = sign
                vrf_output = hashlib.sha256(vrf_proof).hexdigest()
                vrf_output_int = int(vrf_output, 16)
                
                creator_key = new_block_dict["creator"]

                block_stakes = {}
                for stake in newBlock.stakers:
                    vk = VerifyingKey.from_pem(stake.staker)
                    try:
                        print(f"\n{str(stake)}\n")
                        vk.verify(stake.sign, str(stake).encode())
                    except BadSignatureError as e:
                        print(f"\nInvalid Block (Stake Signature Error) {e}\n")
                        return

                    block_stakes[stake.staker] = block_stakes.get(stake.staker, 0) + stake.amt

                # The block's (signed) stake list is the epoch's staker set. It must not
                # drop or alter any stake we already know about, otherwise a creator
                # could omit rivals to make itself the leader.
                for pk, amt in self.current_stakers.items():
                    if block_stakes.get(pk) != amt:
                        print("\nInvalid Block (stake list omits or alters a known stake)\n")
                        return

                if block_stakes.get(creator_key) != newBlock.staked_amt:
                    print("\nInvalid Block (creator stake mismatch)\n")
                    return

                if elect_leader(Chain.instance.epoch_seed(), block_stakes) != creator_key:
                    raise VrfThresholdException("creator is not the elected leader")
                newBlock.seed = Chain.instance.epoch_seed()
                newBlock.vrf_output = vrf_output
                newBlock.vrf_proof = vrf_proof

            except VrfThresholdException as e:
                print(f"\nInvalid Block (VRF_OUTPUT>THRESHOLD), {e}\n")
                return
            
                
            for transaction in newBlock.transactions:
                if transaction.receiver == "invoke":
                    if not self.valid_invoke_transaction(transaction.payload):
                        return
                if transaction.receiver == "deploy":
                    if not self.valid_deploy_transaction(transaction.payload):
                        return

            newBlock.creator = new_block_dict["creator"]
            Chain.instance.chain.append(newBlock)
            asyncio.create_task(self.emit_event({"type": "block_appended", "block": newBlock.to_dict_with_stakers()}))
            print("\n\n Block Appended \n\n")
            self.last_epoch_end_ts = datetime.now()

            for transaction in newBlock.transactions:
                if transaction.receiver == "deploy":
                    self.deploy_contract(transaction)

            async with self.mem_pool_lock:
                for transaction in list(self.mem_pool):
                    if newBlock.transaction_exists_in_block(transaction):
                        self.mem_pool.remove(transaction)
            
            async with self.file_hashes_lock:
                for hash in list(self.file_hashes.keys()):
                    if newBlock.cid_exists_in_block(hash):
                        self.file_hashes.pop(hash, None)
            
            self.staked_amt = 0
            async with self.curr_stakers_condition:
                self.current_stakers.clear()
                self.current_stakes.clear()

            await self.broadcast_message(msg)
            if self.activate_disk_save == "y":
                self.save_chain_to_disk()

        elif t == "slash_announcement":
            block1_dict = msg.get("evidence1")
            block1_sign = msg.get("block1_sign")
            block2_dict = msg.get("evidence2")
            block2_sign = msg.get("block2_sign")
            pos = msg.get("pos")
            
            if not all([block1_dict, block1_sign, block2_dict, block2_sign, pos is not None]):
                return
            
            block1 = self.block_dict_to_block(block1_dict)
            try:
                block1.sign = base64.b64decode(block1_sign)
            except Exception:
                return
            
            if not hasattr(block1, 'creator') or not block1.creator:
                return
            
            vk = VerifyingKey.from_pem(block1.creator)
            
            block2 = self.block_dict_to_block(block2_dict)
            try:
                block2.sign = base64.b64decode(block2_sign)
            except Exception:
                return

            if pos < 0 or pos >= len(Chain.instance.chain):
                return

            block1_exists = Chain.instance.chain[pos].is_equal(block1)
            block2_exists = Chain.instance.chain[pos].is_equal(block2)
            if not (block1_exists or block2_exists):
                return

            err1, err2 = False, False

            try:
                vk.verify(block1.sign, str(block1).encode())
            except BadSignatureError:
                print("\nBad signature on block 1\n")
                err1 = True
            try:
                vk.verify(block2.sign, str(block2).encode())
            except BadSignatureError:
                print("\nBad signature on block 2\n")
                err2 = True

            if err1 and err2:
                print(f"\nInvalid Slashing Evidence")
                return
            
            elif not(err1 or err2) and Chain.instance.chain[pos].is_valid:  # Both Signatures are correct and not slashed yet
                print(f"\nBlock {pos} slashed\n")
                Chain.instance.chain[pos].is_valid = False
                Chain.instance.chain[pos].slash_creator = True
                asyncio.create_task(self.emit_event({"type": "node_slashed", "creator": Chain.instance.chain[pos].creator, "block_pos": pos}))
                await self.broadcast_message(msg)

            # Fork still exists but longest chain will win

            elif (err1 and not err2 and block1_exists) or (err2 and not err1 and block2_exists):
                Chain.instance.chain = Chain.instance.chain[:pos]
                # We trim the chain, eventually when a longer chain arrives it will replace this, but this is unlikely too since we don't share slash_announcement in such cases
                # hmm this means err1 exists but block1 also exists so we trim back to before that block
                # :pos is not included

        elif t == "chain_request":
            if not Chain.instance:
                return

            pkt = {
                "type": "chain",
                "id": str(uuid.uuid4()),
                "chain": Chain.instance.to_block_dict_list()
            }
            await websocket.send(json.dumps(pkt))

        elif t == "chain":
            print("Received a Chain")
            block_dict_list = msg.get("chain")
            if not block_dict_list:
                return
            
            block_list = []

            for block_dict in block_dict_list:
                block = self.block_dict_to_block(block_dict)
                if block is None:
                    print("\nInvalid Chain (malformed block)\n")
                    return
                block_list.append(block)

            if not isvalidChain(block_list):
                print("\nInvalid Chain\n")
                return

            # If chain doesn't already exist we assign this as the chain
            if not self.chain:
                self.chain = Chain(blockList=block_list)
                if self.activate_disk_save == "y":
                    self.save_chain_to_disk()
                
            else:
                pos = Chain.instance.checkEquivalence(block_list)
                if pos != -1:
                    block1 = Chain.instance.chain[pos]
                    block2 = block_list[pos]

                    if block1.creator != block2.creator:  # Ordinary fork: different leaders
                        l1 = len(Chain.instance.chain)
                        l2 = len(block_list)
                        if l2 > l1:
                            Chain.instance.rewrite(block_list)
                            if self.activate_disk_save == "y":
                                self.save_chain_to_disk()
                    else:  # Same creator, two different blocks at one height: double-sign
                        await self.verify_and_slash(block1, block2, pos, block_list)
                        
                elif weight_of_chain(Chain.instance.chain) < weight_of_chain(block_list):
                    Chain.instance.rewrite(block_list)
                    print("\nCurrent chain replaced by heavier chain\n")
                    if self.activate_disk_save == "y":
                        self.save_chain_to_disk()
                
                else:
                    print("\nCurrent Chain heavier than received chain\n")

            async with self.mem_pool_lock:
                for transaction in list(self.mem_pool):
                    if Chain.instance.transaction_exists_in_chain(transaction):
                        self.mem_pool.remove(transaction)
            
            async with self.file_hashes_lock:
                for hash in list(self.file_hashes.keys()):
                    if Chain.instance.cid_exists_in_chain(hash):
                        self.file_hashes.pop(hash, None)

    async def verify_and_slash(self, block1:Block, block2:Block, pos:int, block_list:List[Block]):
        vk=VerifyingKey.from_pem(block1.creator)
        sign1=block1.sign
        sign2=block2.sign
        err1, err2=False, False

        try:
            vk.verify(sign1, str(block1).encode())
        except BadSignatureError:
            print("\nBad signature on block 1\n")
            err1=True
        try:
            vk.verify(sign2, str(block2).encode())
        except BadSignatureError:
            print("\nBad signature on block 2\n")
            err2=True
        

        if(err1 and not err2): # Unlikely since I'm checking blocks as they arrive
            Chain.instance.rewrite(block_list)
            return
        
        elif err2 and not err1: # Fault with arrived chain
            return
        
        Chain.instance.chain[pos].is_valid=False
        Chain.instance.chain[pos].slash_creator=True
        asyncio.create_task(self.emit_event({"type": "node_slashed", "creator": Chain.instance.chain[pos].creator, "block_pos": pos}))

        pkt={
            "type":"slash_announcement",
            "id":str(uuid.uuid4()),
            "evidence1":block1.to_dict_with_stakers(),
            "evidence2":block2.to_dict_with_stakers(),
            "block1_sign":base64.b64encode(block1.sign).decode(),
            "block2_sign":base64.b64encode(block2.sign).decode(),
            "pos":pos
        }
        await self.broadcast_message(pkt)
        # Now the receiver should make sure that the block1 creator signed both the blocks and it is he that is penalized in slash_block, also check my signature 
        # Then if Chain.instance.chain[pos]==block1 or block2 then make that block invalid and slash the creator
        
    async def handle_connections(self, websocket):
        """
            We handle our server connections from here.
            Primary job is to simply read messages and send it to 
            handle_messages function
        """
        peer_addr=(websocket.remote_address[0], websocket.remote_address[1])
        self.server_connections.add(websocket)

        print(f"Inbound Connection from {peer_addr[0]}:{peer_addr[1]}")
        
        try:
            async for raw in websocket:
                msg=json.loads(raw)
                await self.handle_messages(websocket, msg)

        except websockets.exceptions.ConnectionClosed:
            print(f"Inbound Connection Closed: {peer_addr}")

        finally:
            self.server_connections.discard(websocket)
            self.connection_peer_keys.pop(websocket, None)
            await websocket.close()
            await websocket.wait_closed()

    async def broadcast_message(self, pkt):
        # For broadcasting messages to all the connections we have

        latency_ms = getattr(self, "network_latency_ms", 0)
        if latency_ms > 0:
            await asyncio.sleep(latency_ms / 1000)

        targets=self.server_connections | self.client_connections
        for ws in targets:
            if getattr(self, "connection_peer_keys", {}).get(ws) in getattr(self, "attack_blocked_peer_keys", set()):
                continue
            try:
                await ws.send(json.dumps(pkt))

            except Exception as e:
                print(f"Error broadcasting: {e}")
                if ws in self.server_connections:
                    self.server_connections.discard(ws)
                else:
                    normalized_endpoint = normalize_endpoint((ws.remote_address[0], ws.remote_address[1]))
                    self.client_connections.discard(ws)
                    self.outbound_peers.discard(normalized_endpoint)
                    self.got_pong.pop(ws, None)
                    self.have_sent_peer_info.pop(ws, None)
                await ws.close()
                await ws.wait_closed()

    async def emit_event(self, event: dict):
        """
            Pushes an event to every browser client connected to the
            /events websocket (webapi/events.py). Best-effort and
            fire-and-forget by design (always called via
            asyncio.create_task, never awaited directly) - a bug or slow
            client here must never affect consensus-critical code paths.
        """
        if not self.event_subscribers:
            return
        msg = json.dumps(event)
        dead = set()
        for ws in self.event_subscribers:
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        self.event_subscribers -= dead

    async def set_attack_partition(self, peer_keys):
        self.attack_blocked_peer_keys.update(peer_keys)
        sockets = [ws for ws, key in self.connection_peer_keys.items() if key in self.attack_blocked_peer_keys]
        for ws in sockets:
            await ws.close(code=4003, reason="peer isolated by Attack Lab")
        await self.emit_event({"type": "attack_state", "attack": "partition", "blocked_peers": len(self.attack_blocked_peer_keys)})

    async def heal_attack_partition(self):
        restored = set(self.attack_blocked_peer_keys)
        self.attack_blocked_peer_keys.clear()
        for endpoint, (_, public_key) in list(self.known_peers.items()):
            if public_key in restored and endpoint not in self.outbound_peers:
                asyncio.create_task(self.connect_to_peer(*endpoint))
        await self.emit_event({"type": "attack_state", "attack": "partition", "blocked_peers": 0})

    async def set_network_latency(self, latency_ms):
        self.network_latency_ms = latency_ms
        await self.emit_event({"type": "attack_state", "attack": "latency", "latency_ms": latency_ms})

    async def set_transaction_censorship(self, receiver_key, enabled):
        if enabled:
            self.censored_receivers.add(receiver_key)
            async with self.mem_pool_lock:
                self.mem_pool = [tx for tx in self.mem_pool if tx.receiver != receiver_key]
        else:
            self.censored_receivers.discard(receiver_key)
        await self.emit_event({"type": "attack_state", "attack": "censorship", "receiver": receiver_key, "enabled": enabled})

    async def create_and_broadcast_tx(self, receiver_public_key, payload):
        """
            Function to create and broadcast transactions
        """
        if receiver_public_key in self.censored_receivers:
            raise ValueError("Transaction receiver is currently censored by this peer")
        transaction=Transaction(payload, self.wallet.public_key_pem, receiver_public_key)
        transaction_str=str(transaction)
        
        signature=self.wallet.private_key.sign(
            transaction_str.encode(),
        )

        transaction.sign=signature

        signature_b64=base64.b64encode(signature).decode()
        # b64encode returns bytes, Decode converts bytes to string
        
        pkt={
            "type":"new_tx",
            "id":str(uuid.uuid4()),
            "transaction":transaction_str,
            "sign":signature_b64,
            "sender_pem":self.wallet.public_key_pem # Already available as a pem string as defined in constructor
        }
        
        self.seen_message_ids.add(pkt["id"])
        if Chain.instance.transaction_exists_in_chain(transaction):
            return None

        async with self.mem_pool_lock:
                self.mem_pool.append(transaction)

        print("Transaction Created", transaction)
        print("\n")
        await self.broadcast_message(pkt)
        return transaction

    def get_contract_state(self, contract_id):
        for block in reversed(Chain.instance.chain):
            for transaction in reversed(block.transactions):
                if transaction.receiver == "invoke" and transaction.payload[0] == contract_id:
                    return transaction.payload[3]
        return {}

    async def user_input_handler(self):
        """
            A function to constantly take input from the user 
            about whom to send and how much
        """
        while True:
            print("Block Chain Menu\n***************")
            if(self.staker):
                print("0) Quit\n1) Add Transaction\n2) View balance\n3) Print Chain\n4) Print Pending Transactions\n5) Print Current Stakers\n6) Time since last epoch\n7) Send Files\n8) Download Files\n9) Stake\n")
            else:
                print("0) Quit\n1) Add Transaction\n2) View balance\n3) Print Chain\n4) Print Pending Transactions\5) Print Current Stakers\n6) Time since last epoch\n7) Send Files\n8) Download Files\n")

            ch= await asyncio._get_running_loop().run_in_executor(
                None, input, "Enter Your Choice: "
            )
            try:
                ch=int(ch)
            except:
                print("\nPlease enter a valid number!!!\n")

            if ch==1:
                rec = await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter Receiver's Name or Public Key: "
                )

                if rec == "deploy":
                    contract_code = get_contract_code_from_notepad()
                    if not contract_code:
                        print("Contract code field is empty")
                        continue
                    gas_used = len(contract_code)//10 + BASE_DEPLOY_COST
                    amount = gas_used * GAS_PRICE
                    payload = [contract_code, amount]

                    if amount<=Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(rec, payload)
                    else:
                        print("Insufficient Account Balance")
                elif rec == "invoke":
                    contract_id = await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Contract Id: "
                    )
                    if contract_id not in self.contractsDB.contracts:
                        print("No such contract found...")
                        continue

                    func_name = await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Function Name: "
                    )

                    args = []
                    loop = asyncio.get_running_loop()
                    arg_number = 1
                    while True:
                        arg = await loop.run_in_executor(None, input, f"Enter argument {arg_number} (or \\q to finish): ")
                        if arg.strip() == "\\q":
                            break
                        try:
                            parsed_arg = ast.literal_eval(arg)
                        except Exception:
                            parsed_arg = arg
                        args.append(parsed_arg)
                        arg_number += 1

                    response = self.run_contract([contract_id, func_name, args])
                    if(response["error"] != None):
                        print("Error: ", response["error"])
                        continue
                    state = response["state"]
                    gas_used = response["gas_used"]
                    amount = gas_used * GAS_PRICE

                    payload = [contract_id, func_name, args, state, amount]

                    if amount<=Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(rec, payload)
                    else:
                        print("Insufficient Account Balance")
                else:
                    amt= await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Amount to send: "
                    )

                    receiver_public_key = self.name_to_public_key_dict.get(rec.lower().strip())

                    if receiver_public_key is None:
                        rec_split = rec.split("\\n")
                        rec_refined = "\n".join(rec_split)
                        exist = 0
                        for (nme, pk) in self.name_to_public_key_dict.items():
                            if pk == rec_refined:
                                receiver_public_key = pk
                                exist = 1
                                break
                        if exist == 0:
                            print("No person available in directory with provided name or public key...")
                            continue
                    
                    try:
                        amt=float(amt)
                    except ValueError:
                        print("Amount must be a number")
                        continue

                    if(amt<=0):
                        print("\nAmount must be positive\n")
                        continue

                    if amt<=Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(receiver_public_key, amt)
                    else:
                        print("Insufficient Account Balance")
            
            elif ch==2:
                print("Account Balance =",Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)))

            elif ch==3:
                i=0
                # We print all the blocks
                if(not Chain.instance):
                    print("\nChain hasn't been initialized yet\n")
                    continue
                for block in Chain.instance.chain:
                    print(f"block{i}: {block}\n")
                    i+=1

            elif ch==4:
                i=0
                for transaction in self.mem_pool:
                    print(f"transaction{i}: {transaction}\n\n")
                    i+=1

            elif ch==5:
                async with self.curr_stakers_condition:
                    print("\n")
                    for key in self.current_stakers:
                        print(f"{key}:{self.current_stakers[key]}\n")
                    print("\n")

            elif ch==6:
                print(f"\n{(datetime.now()-self.last_epoch_end_ts).seconds}\n")

            elif ch==7:
                desc= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter description of file: "
                )
                path= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter path of file: "
                )
                pkt=await self.uploadFile(desc, path)
                await self.broadcast_message(pkt)

            elif ch==8:
                cid= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter cid of file: "
                )
                path= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter path to download the file: "
                )
                download_ipfs_file_subprocess(cid, path)

            elif ch==9:
                if(not self.staker):
                    continue

                amt= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter Amount to stake: "
                )

                result = await self.stake_coin(amt)
                if result["ok"]:
                    print(f"Creating block in {result['creating_block_in_seconds']} seconds")
                else:
                    print(f"\n{result['error']}\n")

            elif ch==0:
                print("Quitting...")
                break
    
    async def uploadFile(self, desc: str, path:str):
        file_path=Path(path)
        if(not file_path.is_file()):
            print("\nFile doesn't exist\n")
            return

        if not self.daemon_process: 
            self.start_daemon()
        
        cid, name = await asyncio.to_thread(addToIpfs, path)
        if(not(cid and name)):
            return
        
        print(f"\nNew File Created : {cid}\n")
        pkt={
            "type":"file",
            "id":str(uuid.uuid4()),
            "desc":desc,
            "cid":cid
        }
        
        self.seen_message_ids.add(pkt["id"])
        async with self.file_hashes_lock:
            self.file_hashes[cid]=desc
        return pkt

    def init_repo(self):
        """
            Creates a ipfs repo of name ending in ipfs_port_no eg ipfs_5000 
        """
        if not self.repo_path.exists():
            subprocess.run(["ipfs", "init"], env=self.env, check=True)
            print("\nIPFS repo created\n")

    def configure_ports(self):
        subprocess.run(["ipfs", "config", "Addresses.API", f"/ip4/127.0.0.1/tcp/{self.ipfs_port}"], env=self.env, check=True)
        subprocess.run(["ipfs", "config", "Addresses.Gateway", f"/ip4/127.0.0.1/tcp/{self.gateway_port}"], env=self.env, check=True)
        subprocess.run([
            "ipfs", "config", "Addresses.Swarm", "--json",
            f'["/ip4/127.0.0.1/tcp/{self.swarm_tcp}", "/ip4/127.0.0.1/udp/{self.swarm_udp}/quic"]'
        ], env=self.env, check=True)
        print("\nConfigured Ports\n")

    def start_daemon(self):
        self.daemon_process= subprocess.Popen(["ipfs", "daemon"], env=self.env)
        print("\nIPFS Daemon Started\n")

    def stop_daemon(self):
        if self.daemon_process:
            self.daemon_process.terminate()
            self.daemon_process.wait()

    async def connect_to_peer(self, host, port):
        """
            Function to form an outbound connection to the given host:port
            and handle messages that come form this connection
            Also initiates the handshake
        """

        endpoint=(host, port)
        if endpoint in self.outbound_peers or endpoint==(self.host, self.port):
            return

        uri=f"ws://{host}:{port}"
        
        websocket = None
        try:
            websocket=await websockets.connect(uri)
            self.client_connections.add(websocket)
            self.outbound_peers.add(endpoint)
            self.have_sent_peer_info[websocket]=False

            print(f"Outbound connection formed to {host}:{port}")
            
            pkt = None
            # If connecting first time to the network, broadcasts node information to the entire network
            if Chain.instance == None:
                pkt={
                    "type":"add_peer",
                    "id":str(uuid.uuid4()),
                    "data":{
                        "host":self.host,
                        "port":self.port,
                        "name":self.name,
                        "public_key":self.wallet.public_key_pem
                    }
                }
            else:
                pkt={
                    "type":"ping",
                    "id":str(uuid.uuid4()),
                } 

            self.seen_message_ids.add(pkt["id"])
            await websocket.send(json.dumps(pkt))

            async for raw in websocket:
                msg=json.loads(raw)
                await self.handle_messages(websocket, msg)
        except Exception as e:
            print(f"Failed to connect to {host}:{port} ::: {e}")
        finally:
            self.client_connections.discard(websocket)
            self.connection_peer_keys.pop(websocket, None)
            self.outbound_peers.discard(endpoint)
            self.got_pong.pop(websocket, None)
            self.have_sent_peer_info.pop(websocket, None)
            if(websocket):
                await websocket.close()
                await websocket.wait_closed()

    async def discover_peers(self):
        """
            Maintains up to MAX_CONNECTIONS peers.
            Connects only to fill the pool if under MAX_CONNECTIONS.
        """

        while True:
            if len(self.outbound_peers) < MAX_CONNECTIONS:
                potential_peers = {
                    endpoint for endpoint in self.known_peers
                    if endpoint not in self.outbound_peers and endpoint != (self.host, self.port)
                }
                while len(self.outbound_peers) < MAX_CONNECTIONS and potential_peers:
                    new_peer = get_random_element(potential_peers)
                    potential_peers.discard(new_peer)
                    if new_peer:
                        asyncio.create_task(self.connect_to_peer(*new_peer))
                        await asyncio.sleep(1)
            await asyncio.sleep(30)

    async def gossip_peer_sampler(self):
        """
            Every 60s, drops one existing peer and connects to one new peer.
        """
        while True:
            await asyncio.sleep(60)
            if len(self.known_peers) <= len(self.outbound_peers) or len(self.outbound_peers) < MAX_CONNECTIONS:
                continue  # Nothing to swap

            # Disconnect one random client connection
            to_drop = get_random_element(self.client_connections)
            if to_drop:
                print(f"Gossip Sampling: Disconnecting {to_drop.remote_address}")
                self.client_connections.discard(to_drop)
                normalized_endpoint = normalize_endpoint((to_drop.remote_address[0], to_drop.remote_address[1]))
                self.outbound_peers.discard(normalized_endpoint)
                self.got_pong.pop(to_drop, None)
                self.have_sent_peer_info.pop(to_drop, None)
                await to_drop.close()
                await to_drop.wait_closed()

            # Connect to a new peer (not already connected)
            potential_peers = {
                endpoint for endpoint in self.known_peers
                if endpoint not in self.outbound_peers and endpoint != (self.host, self.port)
            }

            if potential_peers:
                new_peer = get_random_element(potential_peers)
                if new_peer:
                    print(f"Gossip Sampling: Connecting to new peer {new_peer}")
                    asyncio.create_task(self.connect_to_peer(*new_peer))

    async def send_stake_announcements(self, amt: int):
        """
            Used for sending stake announcements
        """
        new_stake=Stake(self.wallet.public_key_pem, amt)
        stake_dict=new_stake.to_dict()

        sign=self.wallet.private_key.sign(str(new_stake).encode())
        new_stake.sign=sign

        stake_dict["sign"]=base64.b64encode(sign).decode()
        pkt={
            "id":str(uuid.uuid4()),
            "type":"stake_announcement",
            "public_key":self.wallet.public_key_pem,
            "stake":stake_dict
        }

        self.seen_message_ids.add(pkt["id"])
        async with self.curr_stakers_condition:
            self.current_stakers[self.wallet.public_key_pem]=amt
            self.current_stakes.add(new_stake)

        self.staked_amt=amt
        asyncio.create_task(self.emit_event({"type": "stake_registered", "staker": self.wallet.public_key_pem, "amount": amt}))
        print("Stake Created")
        await self.broadcast_message(pkt)

    async def stake_coin(self, amt: int):
        """
            Shared staking logic used by both the CLI menu (option 9) and the
            web API - keeps epoch-timing/balance rules in one place instead
            of duplicated, so a fix only has to happen once.
            Returns {"ok": True} or {"ok": False, "error": "..."}.
        """
        if not self.staker:
            return {"ok": False, "error": "node is not a staker"}

        currTime=datetime.now()
        time_since=currTime-self.last_epoch_end_ts
        if(self.staked_amt>0):
            return {"ok": False, "error": "already staked this epoch"}

        if(time_since>timedelta(seconds=EPOCH_TIME*5/6)):
            if(time_since>timedelta(seconds=EPOCH_TIME*7/6)):
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.current_stakers.clear()
                self.current_stakes.clear()
                time_since = timedelta(seconds=0)
            else:
                time_till_reset = int(EPOCH_TIME*7/6 - time_since.total_seconds())
                return {"ok": False, "error": f"stake registration period closed, time till next epoch: {time_till_reset}"}

        try:
            amt=int(amt)
        except (TypeError, ValueError):
            return {"ok": False, "error": "amount must be a valid integer"}

        if(amt>Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes))):
            return {"ok": False, "error": "insufficient balance"}

        if(amt<=0):
            return {"ok": False, "error": "amount must be positive"}

        await self.send_stake_announcements(amt)
        self.staked_amt=amt
        time_left=EPOCH_TIME-time_since.seconds
        print(f"Creating block in {time_left} seconds")
        asyncio.create_task(self.create_blocks(time_left))
        return {"ok": True, "creating_block_in_seconds": time_left}

    def build_faucet_tx(self, amount):
        """
            Faucet mint to this node. "Genesis" isn't a real keypair - it is
            signed with the well-known faucet key so peers can verify it
            (see FAUCET_SIGNING_KEY's docstring).
        """
        from shared_blockchain_structures import FAUCET_SIGNING_KEY
        faucet_tx=Transaction(amount, "Genesis", self.wallet.public_key_pem)
        faucet_tx.sign=FAUCET_SIGNING_KEY.sign(str(faucet_tx).encode())
        return faucet_tx

    async def broadcast_faucet_tx(self, faucet_tx):
        async with self.mem_pool_lock:
            self.mem_pool.append(faucet_tx)
        pkt={
            "type": "new_tx",
            "id": faucet_tx.id,
            "transaction": json.dumps(faucet_tx.to_dict()),
            "sign": base64.b64encode(faucet_tx.sign).decode(),
            "sender_pem": "Genesis"
        }
        # Registered before broadcasting so a relay of our own message is
        # dropped by handle_messages instead of double-appending to mem_pool.
        self.seen_message_ids.add(pkt["id"])
        await self.broadcast_message(pkt)

    async def handle_peer_left(self, host, port):
        """
            Signalling server says a room member is gone: forget it so the
            dashboard's peer list/topology shrinks, and tell browsers.
        """
        try:
            endpoint=normalize_endpoint((host, port))
        except OSError:
            endpoint=(host, int(port))
        info=self.known_peers.pop(endpoint, None)
        self.outbound_peers.discard(endpoint)
        if info:
            print(f"Peer left room: {info[0]} ({endpoint[0]}:{endpoint[1]})")
            asyncio.create_task(self.emit_event({"type": "peer_left", "peer": {"host": endpoint[0], "port": endpoint[1], "name": info[0]}}))

    async def auto_stake_loop(self, poll_seconds=5):
        """
            Runs on every staker in every room; on/off via AUTO_STAKE env at
            startup and the dashboard toggle (self.auto_stake) afterwards:
            - a node with no coins asks the faucet once, so joiners can
              become validators (the room's first node holds the genesis
              grant and stakes straight away);
            - once it has a balance it stakes half of it each epoch, so the
              network keeps producing blocks without clicking "Add stake".
            stake_coin() enforces the epoch rules; failures just retry.
        """
        funded=False
        while True:
            await asyncio.sleep(poll_seconds)
            try:
                if not self.auto_stake or self.staked_amt>0:
                    continue
                # Let the last block reach every peer first. A stake announced
                # ahead of it is wiped by receivers when the block lands, so
                # our stake is missing from their staker set and two nodes end
                # up electing different leaders (forks the chain).
                if (datetime.now()-self.last_epoch_end_ts).total_seconds()<AUTO_STAKE_SETTLE_SECONDS:
                    continue
                balance=Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes))
                if balance>0:
                    await self.stake_coin(max(1, balance//2))
                elif not funded and not any(tx.receiver==self.wallet.public_key_pem for tx in self.mem_pool):
                    funded=True
                    faucet_tx=self.build_faucet_tx(50)
                    self.auto_faucet_tx_id=faucet_tx.id
                    await self.broadcast_faucet_tx(faucet_tx)
            except Exception:
                traceback.print_exc()

    async def restart_epoch(self):
        while True:
            await asyncio.sleep(EPOCH_TIME/2)
            currTime=datetime.now()
            if(currTime-self.last_epoch_end_ts>timedelta(seconds=EPOCH_TIME*7/6)):
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.current_stakers.clear()
                self.current_stakes.clear()

    async def create_blocks(self, time):
        if(not self.staker):
            print(self.staker)
            return
    
        await asyncio.sleep(time)
        if(len(self.current_stakers)<=0):
            print("\nNo stakers\n")
            self.last_epoch_end_ts=datetime.now()
            self.staked_amt=0
            return
        
        transactions_in_mem_pool=self.mem_pool
        pending_transactions=[]
        for transaction in transactions_in_mem_pool:
            if(not Chain.instance.transaction_exists_in_chain(transaction)):
                pending_transactions.append(transaction)

        # No early-return on an empty mempool here: a PoS chain still needs
        # to produce (possibly empty) blocks every epoch to rotate stakers
        # and pay out the miner reward, regardless of whether anyone
        # happened to send a transaction that epoch.
        print("\nRunning vrf\n")
        async with self.curr_stakers_condition:# So that no new stakes don't comes in
            seed=Chain.instance.epoch_seed()
            vrf_proof=self.wallet.private_key.sign(seed.encode())
            vrf_output=hashlib.sha256(vrf_proof).hexdigest()
            vrf_output_int=int(vrf_output, 16)
            # Deterministic election (see elect_leader): every staker computes
            # the same winner from the same seed and stakes, so exactly one
            # node mints this epoch's block.
            leader=elect_leader(seed, self.current_stakers)
            if(leader!=self.wallet.public_key_pem):
                print("\nYou've lost\n")
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.current_stakers.clear()
                self.current_stakes.clear()
                return
            
            #The following code is for the winner
            print("\nYou won\n")
            newBlock=Block(Chain.instance.lastBlock.hash, pending_transactions)
            newBlock.files=self.file_hashes.copy()
            newBlock.seed=seed
            newBlock.vrf_proof=vrf_proof
            Chain.instance.chain.append(newBlock)
            newBlock.staked_amt=self.staked_amt
            newBlock.creator=self.wallet.public_key_pem
            newBlock.stakers=self.current_stakers
            

            self.last_epoch_end_ts=datetime.now()
            print("Block Appended")

            for transaction in newBlock.transactions:
                if transaction.receiver == "deploy":
                    self.deploy_contract(transaction)

            newBlock.stakers=list(self.current_stakes)

            self.staked_amt=0
            self.current_stakers.clear()
            self.current_stakes.clear()

            sign=self.wallet.private_key.sign(str(newBlock).encode())
            newBlock.sign=sign

            vrf_proof_b64=base64.b64encode(vrf_proof).decode()
            sign_b64=base64.b64encode(sign).decode()

            print(f"\n{newBlock.to_dict_with_stakers()}\n")
            pkt={
                "type":"new_block",
                "id":str(uuid.uuid4()),
                "block":newBlock.to_dict_with_stakers(),
                "vrf_proof":vrf_proof_b64,
                "sign":sign_b64,
            }

            self.seen_message_ids.add(pkt["id"])
            asyncio.create_task(self.emit_event({"type": "block_appended", "block": newBlock.to_dict_with_stakers()}))
            await self.broadcast_message(pkt)
            if self.activate_disk_save == "y":
                self.save_chain_to_disk()
        self.last_epoch_end_ts=datetime.now()

        async with self.mem_pool_lock:
            for transaction in list(self.mem_pool):
                if newBlock.transaction_exists_in_block(transaction):
                    self.mem_pool.remove(transaction)

        async with self.file_hashes_lock:
            for hash in list(self.file_hashes.keys()):
                if newBlock.cid_exists_in_block(hash):
                    self.file_hashes.pop(hash, None)
                                                       
    async def find_longest_chain(self):
        """
            We routinely check every 30 seconds, every other chain and we replace
            ours with theirs if theirs is >= ours
        """
        while True:
            pkt={
                "type":"chain_request",
                "id":str(uuid.uuid4())
            }
            self.seen_message_ids.add(pkt["id"])
            await self.broadcast_message(pkt)
            print("\nSent out chain requests...")
            await asyncio.sleep(60)

    def calculate_contract_id(self, sender, timestamp):
        data = f"{sender}:{timestamp}"
        hash_object = hashlib.sha256(data.encode('utf-8'))
        return hash_object.hexdigest()
        
    def deploy_contract(self, transaction):
        sender = transaction.sender
        timestamp = transaction.ts
        code = transaction.payload[0]
        contract_id = self.calculate_contract_id(sender, timestamp)
        self.contractsDB.store_contract(contract_id, code)
        print("Contract deployed with id: ", contract_id)

    def run_contract(self, payload):
        contract_id, func_name, args = payload[0], payload[1], payload[2]
        code = self.contractsDB.get_contract(contract_id)
        if code is None:
            raise Exception(f"Contract '{contract_id}' not found.")

        state = self.get_contract_state(contract_id)
        executor = SecureContractExecutor(code)
        response = executor.run(func_name, args, state)

        return response

    async def start(self, bootstrap_host=None, bootstrap_port=None, interactive=True):
        # We start the server
        await websockets.serve(self.handle_connections, self.host, self.port)
        # We await the setting up of the server and the handle connections funciton,
        # This returns a websocket server object eventually

        # If bootstrap node is given we connect to it and take its chain
        if bootstrap_host and bootstrap_port:
            normalized_bootstrap_host, normalized_bootstrap_port = normalize_endpoint((bootstrap_host, bootstrap_port))
            asyncio.create_task(self.connect_to_peer(normalized_bootstrap_host, normalized_bootstrap_port))
        else:
            self.chain=Chain(publicKey=self.wallet.public_key_pem, privatekey=self.wallet.private_key)
            self.last_epoch_end_ts=datetime.now()


        reset_task=asyncio.create_task(self.restart_epoch())
        inp_task=asyncio.create_task(self.user_input_handler()) if interactive else None
        consensus_task=asyncio.create_task(self.find_longest_chain())
        disc_task=asyncio.create_task(self.discover_peers())
        sampler_task = asyncio.create_task(self.gossip_peer_sampler())
        if self.staker:
            self.auto_stake=os.environ.get("AUTO_STAKE", "").strip().lower() in ("1", "true", "y", "yes")
            asyncio.create_task(self.auto_stake_loop())


        if inp_task:
            await inp_task
        else:
            await asyncio.Future()

        reset_task.cancel()
        disc_task.cancel()
        consensus_task.cancel()
        sampler_task.cancel()
