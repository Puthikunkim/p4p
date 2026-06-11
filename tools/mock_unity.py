#!/usr/bin/env python3
"""Headless Unity mock client for local development and CI.

Connects to WsSink, sends an Object-Status Manifest (handshake), then prints
any StatusRequests that arrive. It also walks through a fake study session,
pushing a vr_context message on each "step" so the dashboard's VR Context
section updates live. Keeps the connection open until interrupted.

Usage:
    python tools/mock_unity.py [--host HOST] [--port PORT]
    python tools/mock_unity.py --port 9001
    python tools/mock_unity.py --context-interval 4   # advance step every 4 s
    python tools/mock_unity.py --context-interval 0   # disable context (manifest only)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

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

# A fake study walk-through. Each entry is one vr_context payload (free-form
# key/value); the dashboard renders whatever keys appear here.
STEPS = [
    {"scene": "Aisle 1 – Produce", "step": "1 / 4", "instruction": "Pick up the apples", "items_left": 3},
    {"scene": "Aisle 2 – Bakery", "step": "2 / 4", "instruction": "Select the milk", "items_left": 2},
    {"scene": "Aisle 3 – Dairy", "step": "3 / 4", "instruction": "Find the cheese", "items_left": 1},
    {"scene": "Checkout", "step": "4 / 4", "instruction": "Pay for your items", "items_left": 0, "assistance_active": True},
]


async def _recv_loop(ws: Any) -> None:
    async for msg in ws:
        req = json.loads(msg)
        print(f"[mock_unity] StatusRequest: {req}", flush=True)


async def _context_loop(ws: Any, interval: float) -> None:
    i = 0
    while True:
        step = STEPS[i % len(STEPS)]
        await ws.send(json.dumps({"type": "vr_context", "payload": step}))
        print(f"[mock_unity] vr_context: {step['scene']} ({step['step']})", flush=True)
        i += 1
        await asyncio.sleep(interval)


async def run(host: str, port: int, context_interval: float) -> None:
    uri = f"ws://{host}:{port}"
    print(f"[mock_unity] connecting to {uri}", flush=True)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(MANIFEST))
        print("[mock_unity] sent Object-Status Manifest", flush=True)
        tasks = [asyncio.create_task(_recv_loop(ws))]
        if context_interval > 0:
            tasks.append(asyncio.create_task(_context_loop(ws, context_interval)))
        await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument(
        "--context-interval",
        type=float,
        default=6.0,
        help="Seconds between vr_context step changes (0 disables; default: 6)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port, args.context_interval))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
