#!/usr/bin/env python3
"""Headless Unity mock client for local development and CI.

Connects to WsSink, sends an Object-Status Manifest (handshake), then prints
any StatusRequests that arrive. It also:
  - walks a fake study session, pushing a vr_context message per "step", and
  - declares behavioural channels and streams behaviour_sample frames so the
    Behavioural panel updates live and the rule engine has signals to act on.
Keeps the connection open until interrupted.

Usage:
    python tools/mock_unity.py [--host HOST] [--port PORT]
    python tools/mock_unity.py --port 9001
    python tools/mock_unity.py --context-interval 4     # advance step every 4 s
    python tools/mock_unity.py --behaviour-interval 0.5 # stream behaviour at 2 Hz
    python tools/mock_unity.py --context-interval 0 --behaviour-interval 0  # manifest only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
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


# Behavioural channels Unity tracks over the session (Contract 1 channel shape).
# These are merged into the signal manifest so they render, feed the rule engine
# (dim-slow-response on response_latency, fog-idle on idle_time), and get recorded.
BEHAVIOUR_CHANNELS = [
    {"name": "response_latency", "unit": "s", "type": "scalar", "range": {"min": 0, "max": 15},
     "display": {"hint": "stat_card", "label": "Response Latency", "precision": 1, "group": "behavioural"}},
    {"name": "response_accuracy", "unit": "%", "type": "scalar", "range": {"min": 0, "max": 100},
     "display": {"hint": "stat_card", "label": "Response Accuracy", "precision": 0, "group": "behavioural"}},
    {"name": "task_accuracy", "unit": "%", "type": "scalar", "range": {"min": 0, "max": 100},
     "display": {"hint": "stat_card", "label": "Task Accuracy", "precision": 0, "group": "behavioural"}},
    {"name": "idle_time", "unit": "s", "type": "scalar", "range": {"min": 0, "max": 30},
     "display": {"hint": "stat_card", "label": "Idle Time", "precision": 1, "group": "behavioural"}},
    {"name": "clarification_reqs", "unit": "/task", "type": "scalar", "range": {"min": 0, "max": 10},
     "display": {"hint": "stat_card", "label": "Clarification Reqs", "precision": 1, "group": "behavioural"}},
    {"name": "gaze_switching_rate", "unit": "/s", "type": "scalar", "range": {"min": 0, "max": 2},
     "display": {"hint": "stat_card", "label": "Gaze Switching Rate", "precision": 2, "group": "behavioural"}},
]


async def _recv_loop(ws: Any) -> None:
    async for msg in ws:
        req = json.loads(msg)
        print(f"[mock_unity] StatusRequest: {req}", flush=True)


async def _behaviour_loop(ws: Any, interval: float) -> None:
    # Declare the behavioural channels once, then stream values. Latency and idle
    # time oscillate past their rule thresholds so adaptations fire periodically.
    await ws.send(json.dumps({"type": "behaviour_manifest", "payload": {"channels": BEHAVIOUR_CHANNELS}}))
    print(f"[mock_unity] declared {len(BEHAVIOUR_CHANNELS)} behavioural channels", flush=True)
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        sample = {
            "response_latency": round(max(0.0, 4 + 7 * (0.5 + 0.5 * math.sin(t / 6))), 1),
            "idle_time": round(max(0.0, 8 + 12 * (0.5 + 0.5 * math.sin(t / 9 + 1))), 1),
            "task_accuracy": round(70 + 25 * (0.5 + 0.5 * math.sin(t / 8)), 0),
            "response_accuracy": round(65 + 25 * (0.5 + 0.5 * math.sin(t / 8)), 0),
            "clarification_reqs": round(2 * (0.5 + 0.5 * math.sin(t / 5)), 1),
            "gaze_switching_rate": round(0.5 + 0.5 * math.sin(t / 4), 2),
        }
        await ws.send(json.dumps({"type": "behaviour_sample", "payload": sample}))
        await asyncio.sleep(interval)


async def _context_loop(ws: Any, interval: float) -> None:
    i = 0
    while True:
        step = STEPS[i % len(STEPS)]
        await ws.send(json.dumps({"type": "vr_context", "payload": step}))
        print(f"[mock_unity] vr_context: {step['scene']} ({step['step']})", flush=True)
        i += 1
        await asyncio.sleep(interval)


async def run(host: str, port: int, context_interval: float, behaviour_interval: float) -> None:
    uri = f"ws://{host}:{port}"
    print(f"[mock_unity] connecting to {uri}", flush=True)
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(MANIFEST))
        print("[mock_unity] sent Object-Status Manifest", flush=True)
        tasks = [asyncio.create_task(_recv_loop(ws))]
        if context_interval > 0:
            tasks.append(asyncio.create_task(_context_loop(ws, context_interval)))
        if behaviour_interval > 0:
            tasks.append(asyncio.create_task(_behaviour_loop(ws, behaviour_interval)))
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
    parser.add_argument(
        "--behaviour-interval",
        type=float,
        default=1.0,
        help="Seconds between behaviour_sample frames (0 disables; default: 1)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port, args.context_interval, args.behaviour_interval))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
