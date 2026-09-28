import asyncio
import os
from consensus.poa.p2p import Peer as PoAPeer
from consensus.pos.p2p import Peer as PoSPeer
from consensus.pow.p2p import Peer as PoWPeer
from consensus.poa.mal_node import Peer as PoaMalPeer
from consensus.pos.mal_node import Peer as PosMalPeer
from consensus.pow.mal_node import Peer as PowMalPeer


def get_env_or_input(name, prompt, cast=str):
    value = os.getenv(name)
    if value is not None:
        return cast(value)
    return cast(input(prompt))


def get_bool(name, prompt):
    value = os.getenv(name)

    if value is not None:
        value = value.strip().lower()
        if value in ("true", "1", "yes", "y"):
            return True
        if value in ("false", "0", "no", "n"):
            return False
        raise ValueError(
            f"{name} must be one of: true/false, 1/0, yes/no, y/n"
        )

    return input(prompt).strip().lower() == "y"


def start_peer():
    host = get_env_or_input("PEER_HOST", "Enter Host: ")
    port = get_env_or_input("PEER_PORT", "Enter Port: ", int)
    name = get_env_or_input("PEER_NAME", "Enter Name: ")

    consensus = get_env_or_input(
        "CONSENSUS",
        "Enter Consensus[poa/pos/pow] (default : pow): "
    ).strip().lower()

    activate_disk_load = get_env_or_input(
        "DISK_LOAD",
        "Do you like to load saved data if any(y/n): "
    )

    activate_disk_save = get_env_or_input(
        "DISK_SAVE",
        "Do you like to continuously backup data to disk(y/n): "
    )

    action = get_env_or_input(
        "ACTION",
        "Enter 'create' to create a network, 'connect' to connect via host:port, or 'room' to join via signalling server using a room ID (default: create): "
    ).strip().lower()
    
    if not consensus:
        consensus = "pow"

    if not action:
        action = "create"

    bootstrap_host = None
    bootstrap_port = None
    signalling_host = None
    signalling_port = None
    room_id = None

    if action == "connect":
        bootstrap_host = get_env_or_input(
            "BOOTSTRAP_HOST",
            "Enter host to connect: "
        )
        bootstrap_port = get_env_or_input(
            "BOOTSTRAP_PORT",
            "Enter port to connect: ",
            int
        )

    elif action == "room":
        signalling_host = get_env_or_input(
            "SIGNALLING_HOST",
            "Enter signalling server host: "
        )
        signalling_port = get_env_or_input(
            "SIGNALLING_PORT",
            "Enter signalling server port: ",
            int
        )
        room_id = get_env_or_input(
            "ROOM_ID",
            "Enter room ID (share this with teammates to join the same network): "
        )

    peer = None
    if consensus == "poa":
        mal = get_bool("MALICIOUS", "Malicious? (y/n): ")
        
        if(not mal):
            peer = PoAPeer(host, port, name, activate_disk_load, activate_disk_save)
        else:
            peer = PoaMalPeer(host, port, name, activate_disk_load, activate_disk_save)
        peer.name_to_node_id_dict[peer.name.lower()] = peer.node_id
        peer.node_id_to_name_dict[peer.node_id] = peer.name.lower()

    elif consensus == "pos":
        mal = get_bool("MALICIOUS", "Malicious? (y/n): ")

        if not mal:
            staker = get_bool("STAKER", "Staker? (y/n): ")

            peer = PoSPeer(
                host, port, name,
                staker,
                activate_disk_load,
                activate_disk_save
            )
        else:
            peer = PosMalPeer(
                host, port, name,
                True,
                activate_disk_load,
                activate_disk_save
            )

    else:
        mal = get_bool("MALICIOUS", "Malicious? (y/n): ")

        if not mal:
            miner = get_bool("MINER", "Miner? (y/n): ")

            peer = PoWPeer(
                host, port, name,
                miner,
                activate_disk_load,
                activate_disk_save
            )
        else:
            peer = PowMalPeer(
                host, port, name,
                True,
                activate_disk_load,
                activate_disk_save
            )


    try:
        if action == "room":
            asyncio.run(start_via_room(peer, signalling_host, signalling_port, room_id))
        else:
            asyncio.run(peer.start(bootstrap_host, bootstrap_port))
    except KeyboardInterrupt:
        print("\nShutting Down...")


async def start_via_room(peer, signalling_host, signalling_port, room_id):
    """
    Joins the room and stays registered with the signalling server for the
    peer's whole lifetime (same event loop as peer.start()), so nodes that
    join later can still discover this one - not just a one-time snapshot.
    """
    from signalling.client import join_room

    def on_new_peer(peer_info):
        asyncio.create_task(peer.connect_to_peer(peer_info["host"], int(peer_info["port"])))

    initial_peers, _ = await join_room(
        signalling_host, signalling_port, room_id,
        peer.host, peer.port, peer.name, peer.wallet.public_key_pem,
        on_peer_joined=on_new_peer,
    )

    bootstrap_host = bootstrap_port = None
    if initial_peers:
        first = initial_peers[0]
        bootstrap_host, bootstrap_port = first["host"], int(first["port"])
        print(f"\nDiscovered {len(initial_peers)} peer(s) in room '{room_id}', bootstrapping off {first['name']} ({bootstrap_host}:{bootstrap_port})\n")
    else:
        print(f"\nFirst node in room '{room_id}' - starting a new network\n")

    await peer.start(bootstrap_host, bootstrap_port)

if __name__=="__main__":
    start_peer()