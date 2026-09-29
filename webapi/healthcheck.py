"""
Docker healthcheck for a pos peer's web API. Checking the port is open isn't
enough here: run_api_server() starts the Flask app *before* the peer has
decided (via join_room) whether it's creating a fresh genesis or bootstrapping
off another node - so the API responds long before Chain.instance exists.

Other services in the room depend on this one having already claimed genesis
(see docker-compose.yml's peer-alice healthcheck), so "healthy" here means
GET /chain returns at least one block, not just "port open".
"""
import json
import os
import sys
import urllib.request


def check():
    port = int(os.environ.get("PEER_PORT", "5000")) + 1000
    token = os.environ.get("WEBAPI_TOKEN", "")
    req = urllib.request.Request(
        f"http://localhost:{port}/chain",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        data = json.load(resp)
    if not data.get("blocks"):
        raise RuntimeError("chain has no genesis block yet")


if __name__ == "__main__":
    try:
        check()
    except Exception:
        sys.exit(1)
