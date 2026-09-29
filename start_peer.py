import asyncio
import os
import socket
from dotenv import load_dotenv
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


def detect_own_ip():
    """
    Finds this container/machine's own outward-facing IP without needing
    real connectivity - a UDP "connect" just picks the right local
    interface for the OS's routing table, it never actually sends a packet.
    Used for AUTO_DETECT_HOST so a scaled batch of identical containers
    (docker compose up --scale peer-swarm=N) can each advertise their own
    real IP instead of a shared hostname that only resolves to one of them.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def start_peer():
    load_dotenv()  # loads .env into os.environ if present; no-op otherwise

    auto_detect_host = os.getenv("AUTO_DETECT_HOST", "").strip().lower() in ("true", "1", "yes", "y")
    if auto_detect_host:
        host = detect_own_ip()
    else:
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

    interactive = os.getenv("INTERACTIVE", "true").strip().lower() not in ("false", "0", "no", "n")
    
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


    enable_api = (consensus == "pos" and not mal)
    api_port = port + 1000

    try:
        asyncio.run(run_peer(
            peer, action, bootstrap_host, bootstrap_port,
            signalling_host, signalling_port, room_id,
            enable_api, api_port, interactive,
        ))
    except KeyboardInterrupt:
        print("\nShutting Down...")


async def run_peer(peer, action, bootstrap_host, bootstrap_port,
                    signalling_host, signalling_port, room_id,
                    enable_api, api_port, interactive=True):
    if enable_api:
        from webapi.server import run_api_server
        from webapi.events import run_events_server
        loop = asyncio.get_running_loop()
        _, token, limiter, auth_tracker = run_api_server(peer, loop, api_port)
        events_host = os.environ.get("WEBAPI_HOST", "127.0.0.1")
        run_events_server(peer, events_host, api_port + 1, token, limiter, auth_tracker)

    if action == "room":
        from signalling.client import join_room

        def on_new_peer(peer_info):
            asyncio.create_task(peer.connect_to_peer(peer_info["host"], int(peer_info["port"])))

        def on_peer_gone(peer_info):
            asyncio.create_task(peer.handle_peer_left(peer_info["host"], int(peer_info["port"])))

        initial_peers, _ = await join_room(
            signalling_host, signalling_port, room_id,
            peer.host, peer.port, peer.name, peer.wallet.public_key_pem,
            on_peer_joined=on_new_peer,
            on_peer_left=on_peer_gone,
        )

        if initial_peers:
            first = initial_peers[0]
            bootstrap_host, bootstrap_port = first["host"], int(first["port"])
            print(f"\nDiscovered {len(initial_peers)} peer(s) in room '{room_id}', bootstrapping off {first['name']} ({bootstrap_host}:{bootstrap_port})\n")
        else:
            print(f"\nFirst node in room '{room_id}' - starting a new network\n")

    if interactive or not enable_api:
        await peer.start(bootstrap_host, bootstrap_port)
    else:
        await peer.start(bootstrap_host, bootstrap_port, interactive=False)

if __name__=="__main__":
    start_peer()
