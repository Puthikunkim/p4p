#!/usr/bin/env python3
"""Headless Unity mock client for local development and CI.

Connects to WsSink, sends an Object-Status Manifest (handshake), then prints
any StatusRequests that arrive. Keeps the connection open until interrupted.

Usage:
    python tools/mock_unity.py [--host HOST] [--port PORT]
    python tools/mock_unity.py --port 9001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "backend"))

import websockets

MANIFEST = {
    "schema_version": "1.0.0",
    "scene": "debug_scene",
    "runtime": "mock-unity",
    "objects": [
        {
            "id": "light-1",
            "tags": ["ambient_light"],
            "statuses": [
                {
                    "name": "brightness",
                    "type": "continuous",
                    "range": {"min": 0, "max": 100},
                }
            ],
        },
        {
            "id": "fog-1",
            "tags": ["fog"],
            "statuses": [
                {
                    "name": "density",
                    "type": "discrete",
                    "values": ["low", "medium", "high"],
                }
            ],
        },
    ],
    "abstract_actions": [],
}


async def run(host: str, port: int) -> None:
    uri = f"ws://{host}:{port}"
    print(f"[mock_unity] connecting to {uri}", flush=True)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(MANIFEST))
        print("[mock_unity] sent Object-Status Manifest", flush=True)
        async for msg in ws:
            req = json.loads(msg)
            print(f"[mock_unity] StatusRequest: {req}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
