import asyncio
from consensus.poa.p2p import Peer as PoAPeer
from consensus.pos.p2p import Peer as PoSPeer
from consensus.pow.p2p import Peer as PoWPeer
from consensus.poa.mal_node import Peer as PoaMalPeer
from consensus.pos.mal_node import Peer as PosMalPeer
from consensus.pow.mal_node import Peer as PowMalPeer

def start_peer():
    host = input("Enter Host: ")
    port = int(input("Enter Port: "))
    name = input("Enter Name: ")
    consensus = input("Enter Consensus[poa/pos/pow] (default : pow): ")
    activate_disk_load = input("Do you like to load saved data if any(y/n): ")
    activate_disk_save = input("Do you like to continuously backup data to disk(y/n): ")
    action = input("Enter 'create' to create a network, 'connect' to connect via host:port, or 'room' to join via signalling server using a room ID (default: create): ")
    bootstrap_host = None
    bootstrap_port = None
    signalling_host = None
    signalling_port = None
    room_id = None
    if action == "connect":
        bootstrap_host = input("Enter host to connect: ")
        bootstrap_port = int(input("Enter port to connect: "))
    elif action == "room":
        signalling_host = input("Enter signalling server host: ")
        signalling_port = int(input("Enter signalling server port: "))
        room_id = input("Enter room ID (share this with teammates to join the same network): ")
    peer = None
    if consensus == "poa":
        mal=False
        mal_raw_input = input("Malcious? (y/n) ").strip().lower()
        if mal_raw_input == "y":
            mal = True
        elif mal_raw_input == "n":
            mal = False
        if(not mal):
            peer = PoAPeer(host, port, name, activate_disk_load, activate_disk_save)
        else:
            peer = PoaMalPeer(host, port, name, activate_disk_load, activate_disk_save)
        peer.name_to_node_id_dict[peer.name.lower()] = peer.node_id
        peer.node_id_to_name_dict[peer.node_id] = peer.name.lower()

    elif consensus == "pos":
        mal=False
        mal_raw_input = input("Malcious? (y/n) ").strip().lower()
        if mal_raw_input == "y":
            mal = True
        elif mal_raw_input == "n":
            mal = False
        
        if(not mal):
            staker = True
            staker_raw_input = input("Staker? (y/n) ").strip().lower()
            if staker_raw_input == "y":
                staker = True
            elif staker_raw_input == "n":
                staker = False
            peer = PoSPeer(host, port, name, staker, activate_disk_load, activate_disk_save)
        else:
            peer = PosMalPeer(host, port, name, True, activate_disk_load, activate_disk_save)

    else:        
        mal=False
        mal_raw_input = input("Malcious? (y/n) ").strip().lower()
        if mal_raw_input == "y":
            mal = True
        elif mal_raw_input == "n":
            mal = False
        
        if(not mal):
            miner = True
            miner_raw_input = input("Miner? (y/n) ").strip().lower()
            if miner_raw_input == "y":
                miner = True
            elif miner_raw_input == "n":
                miner = False
            peer = PoWPeer(host, port, name, miner, activate_disk_load, activate_disk_save)
        else:
            peer = PowMalPeer(host, port, name, True, activate_disk_load, activate_disk_save)


    enable_api = (consensus == "pos" and not mal)
    api_port = port + 1000

    try:
        asyncio.run(run_peer(
            peer, action, bootstrap_host, bootstrap_port,
            signalling_host, signalling_port, room_id,
            enable_api, api_port,
        ))
    except KeyboardInterrupt:
        print("\nShutting Down...")


async def run_peer(peer, action, bootstrap_host, bootstrap_port,
                    signalling_host, signalling_port, room_id,
                    enable_api, api_port):
    if enable_api:
        from webapi.server import run_api_server
        run_api_server(peer, asyncio.get_running_loop(), api_port)

    if action == "room":
        from signalling.client import join_room

        def on_new_peer(peer_info):
            asyncio.create_task(peer.connect_to_peer(peer_info["host"], int(peer_info["port"])))

        initial_peers, _ = await join_room(
            signalling_host, signalling_port, room_id,
            peer.host, peer.port, peer.name, peer.wallet.public_key_pem,
            on_peer_joined=on_new_peer,
        )

        if initial_peers:
            first = initial_peers[0]
            bootstrap_host, bootstrap_port = first["host"], int(first["port"])
            print(f"\nDiscovered {len(initial_peers)} peer(s) in room '{room_id}', bootstrapping off {first['name']} ({bootstrap_host}:{bootstrap_port})\n")
        else:
            print(f"\nFirst node in room '{room_id}' - starting a new network\n")

    await peer.start(bootstrap_host, bootstrap_port)

if __name__=="__main__":
    start_peer()