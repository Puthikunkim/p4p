"""Phase 9 — end-to-end smoke test.

Proves the full chain — signal in → rule fires → WsSink delivers to a mock
Unity WS client → recorded to SQLite — without any hardware or LSL runtime.

Stack wired in this test
------------------------
  ReplaySource    — reads fixture CSV + manifest, publishes SampleEvents on bus
  RuleRegistry    — loads a single YAML rule from tmp_path/rules/
  RuleEvaluator   — evaluates rules against each sample
  WsSink          — real WebSocket server (port 0 = OS-assigned)
  Recorder        — SQLite persistence via an in-memory tmp path
  mock Unity WS   — a bare websockets client that sends the Object-Status Manifest
                    and collects incoming StatusRequests

No TestClient, no FastAPI app, no external processes.  Pure asyncio + real
network sockets bound to loopback.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

import pytest
import websockets

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import SampleEvent
from vcore.core.schema import ActiveManifests
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry
from vcore.ingestion.replay_source import ReplaySource
from vcore.outbound.ws_sink import WsSink
from vcore.recording.recorder import Recorder
from vcore.recording.sqlite_store import SqliteStore

_FIXTURES = Path(__file__).parent.parent.parent / "tools" / "fixtures"
_MANIFEST_PATH = _FIXTURES / "sample_session.manifest.json"
_CSV_PATH = _FIXTURES / "sample_session.csv"

_OBJECT_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "scene": "smoke_scene",
    "runtime": "mock-unity",
    "objects": [
        {
            "id": "light-1",
            "tags": ["ambient_light"],
            "statuses": [
                {"name": "brightness", "type": "continuous", "range": {"min": 0, "max": 100}}
            ],
        }
    ],
    "abstract_actions": [],
}

_RULE_YAML = """\
id: smoke-dim
schema_version: "1.0.0"
description: "Smoke test rule: high cognitive load dims the light."
enabled: true
when:
  all:
    - signal: cognitive_load
      op: ">="
      threshold: 0.4
then:
  set:
    target:
      tag: ambient_light
    status: brightness
    value: 20
  cooldown_s: 0
"""


@pytest.fixture()
def rules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rules"
    d.mkdir()
    (d / "smoke.yaml").write_text(_RULE_YAML)
    return d


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


async def _mock_unity(port: int, received: list[dict[str, Any]]) -> None:
    """Connect to WsSink, send manifest, collect StatusRequests until cancelled."""
    uri = f"ws://127.0.0.1:{port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(_OBJECT_MANIFEST))
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                received.append(json.loads(msg))
            except TimeoutError:
                break
            except websockets.exceptions.ConnectionClosed:
                break


@pytest.mark.asyncio
async def test_signal_to_unity_and_sqlite(
    rules_dir: Path, data_dir: Path
) -> None:
    """Full chain: replay fixture → rule fires → Unity receives StatusRequest → SQLite records session."""
    bus = EventBus()
    manifests = ActiveManifests()

    # --- engine ---
    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)

    # --- outbound: real WS server on loopback, OS-assigned port ---
    sink = WsSink("127.0.0.1", 0, bus=bus, manifests=manifests)
    await sink.start()
    port = sink.bound_port

    # --- recorder ---
    recorder = Recorder(bus, manifests, data_dir)
    await recorder.start()

    # --- replay source (fast: bump rate to avoid long waits) ---
    source = ReplaySource(
        _MANIFEST_PATH,
        _CSV_PATH,
        bus=bus,
        manifests=manifests,
        stale_timeout_s=30.0,
        loop=True,
    )

    received: list[dict[str, Any]] = []

    try:
        # Start mock Unity client — it connects, sends manifest, waits for requests
        unity_task = asyncio.create_task(_mock_unity(port, received))
        # Give the WS connection time to establish and the manifest to propagate
        await asyncio.sleep(0.1)

        # Start evaluator now that manifests are being populated
        await evaluator.start()

        # Start session before samples flow
        sid = recorder.start_session("smoke-participant")

        # Start streaming samples; CSV has rows with cognitive_load ≥ 0.4 which triggers the rule
        await source.start()

        # Wait up to 3 s for at least one StatusRequest to reach the mock Unity
        deadline = time.monotonic() + 3.0
        while not received and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        # Stop recording before teardown
        await recorder.stop_session()

    finally:
        await source.stop()
        await evaluator.stop()
        unity_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await unity_task
        await sink.stop()
        await recorder.stop()

    # ── assertions ────────────────────────────────────────────────────────────

    assert received, "mock Unity received no StatusRequests — rule did not fire"

    req = received[0]
    assert req["status"] == "brightness"
    assert req["value"] == 20
    assert req["source_rule"] == "smoke-dim"

    # SQLite session was persisted
    store = SqliteStore(data_dir / "sessions.db")
    sessions = store.list_sessions()
    assert any(s["id"] == sid for s in sessions), "session not found in SQLite"
    store.close()


@pytest.mark.asyncio
async def test_rule_not_fired_when_no_object_manifest(
    rules_dir: Path, data_dir: Path
) -> None:
    """Rule must stay disabled (and not fire) if no Object-Status Manifest has arrived."""
    bus = EventBus()
    manifests = ActiveManifests()  # no object manifest

    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)

    fired: list[object] = []

    async def _collect_fired(ev: object) -> None:
        fired.append(ev)

    bus.subscribe(Topics.RULE_FIRED, _collect_fired)

    await evaluator.start()

    manifests.update_signal_manifest(json.loads(_MANIFEST_PATH.read_text()))

    # Publish a sample that would normally trigger the rule
    await bus.publish(
        Topics.SAMPLE,
        SampleEvent(
            stream_name="om.cognitive",
            timestamp=1.0,
            values={"cognitive_load": 0.9, "eeg_alpha_power": 50.0, "affect": "stressed"},
        ),
    )
    await asyncio.sleep(0.05)

    await evaluator.stop()

    assert not fired, f"rule fired despite missing object manifest: {fired}"


@pytest.mark.asyncio
async def test_replay_source_publishes_samples(tmp_path: Path) -> None:
    """ReplaySource publishes SampleEvents to the bus from the fixture CSV."""
    bus = EventBus()
    manifests = ActiveManifests()

    samples: list[SampleEvent] = []

    async def _collect(ev: object) -> None:
        if isinstance(ev, SampleEvent):
            samples.append(ev)

    bus.subscribe(Topics.SAMPLE, _collect)

    source = ReplaySource(
        _MANIFEST_PATH,
        _CSV_PATH,
        bus=bus,
        manifests=manifests,
        stale_timeout_s=30.0,
        loop=False,
    )
    await source.start()

    # Wait for at least 3 samples (fixture CSV has 20 rows; srate=10 → 0.3 s minimum)
    deadline = time.monotonic() + 5.0
    while len(samples) < 3 and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    await source.stop()

    assert len(samples) >= 3, f"expected ≥3 samples, got {len(samples)}"
    first = samples[0]
    assert "cognitive_load" in first.values
    assert isinstance(first.values["cognitive_load"], float)
    assert first.values["affect"] in ("calm", "stressed", "bored", "engaged")
