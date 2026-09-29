"""
Docker healthcheck for the signalling server. A bare TCP connect-and-close
(what the previous healthcheck did) looks like a malformed client to the
websockets server - it logs a scary "did not receive a valid HTTP request"
exception on every single probe, forever, cluttering the logs with nothing
actually wrong. Completing the real websocket handshake and closing
cleanly makes it a normal, silent disconnect instead.
"""
import asyncio
import sys

import websockets


async def check():
    async with websockets.connect("ws://localhost:7000", open_timeout=2):
        pass


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception:
        sys.exit(1)
