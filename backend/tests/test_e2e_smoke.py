"""Phase 9 — end-to-end smoke test.

Proves the full chain — signal in → rule fires → WsSink delivers to a mock
Unity WS client → recorded to SQLite — without any hardware or LSL runtime.

Stack wired in this test
------------------------
  sample injector — loads the fixture signal manifest + publishes SampleEvents on the bus
  RuleRegistry    — loads a single YAML rule from tmp_path/rules/
  RuleEvaluator   — evaluates rules against each sample
  WsSink          — the /ws/runtime handler, driven in-memory (no socket)
  Recorder        — SQLite persistence via an in-memory tmp path
  mock Unity WS   — an in-memory fake that sends the Object-Status Manifest
                    and collects incoming StatusRequests

No TestClient, no FastAPI app, no external processes, no sockets — pure asyncio.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import SampleEvent
from vcore.core.schema import ActiveManifests
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry
from vcore.outbound.ws_sink import WsSink
from vcore.recording.recorder import Recorder
from vcore.recording.sqlite_store import SqliteStore

_FIXTURES = Path(__file__).parent.parent.parent / "tools" / "fixtures"
_MANIFEST_PATH = _FIXTURES / "sample_session.manifest.json"

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


class _FakeUnityWs:
    """In-memory Unity connection driving WsSink.handle_connection (no real socket)."""

    remote_address = "mock-unity:0"

    def __init__(self, received: list[dict[str, Any]]) -> None:
        self._inbox: asyncio.Queue[str] = asyncio.Queue()
        self._received = received

    async def recv(self) -> str:
        return await self._inbox.get()

    async def send(self, data: str) -> None:
        self._received.append(json.loads(data))

    async def client_send(self, frame: str) -> None:
        await self._inbox.put(frame)


async def _mock_unity(sink: WsSink, received: list[dict[str, Any]]) -> None:
    """Drive WsSink.handle_connection: send the manifest, collect forwarded StatusRequests."""
    ws = _FakeUnityWs(received)
    await ws.client_send(json.dumps({"type": "object_status_manifest", "payload": _OBJECT_MANIFEST}))
    await sink.handle_connection(ws)


@pytest.mark.asyncio
async def test_signal_to_unity_and_sqlite(
    rules_dir: Path, data_dir: Path
) -> None:
    """Full chain: sample injected → rule fires → Unity receives StatusRequest → SQLite records session."""
    bus = EventBus()
    manifests = ActiveManifests()

    # --- engine ---
    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)

    # --- outbound: the /ws/runtime handler, driven in-memory ---
    sink = WsSink(bus=bus, manifests=manifests)
    await sink.start()

    # --- recorder ---
    recorder = Recorder(
        bus, manifests,
        xdf_dir=data_dir / "xdf",
        sqlite_path=data_dir / "vcore.db",
    )
    await recorder.start()

    # --- sample injector (replaces a live source: no hardware, no LSL) ---
    async def _inject_samples() -> None:
        while True:
            await bus.publish(
                Topics.SAMPLE,
                SampleEvent(
                    stream_name="sensor.cognitive",
                    timestamp=time.time(),
                    values={"cognitive_load": 0.9, "eeg_alpha_power": 50.0, "affect": "stressed"},
                ),
            )
            await asyncio.sleep(0.05)

    received: list[dict[str, Any]] = []
    inject_task: asyncio.Task[None] | None = None

    try:
        # Mock Unity connects + sends its Object-Status Manifest
        unity_task = asyncio.create_task(_mock_unity(sink, received))
        # Give the connection time to establish and the manifest to propagate
        await asyncio.sleep(0.1)

        # Start evaluator now that the object manifest is populated
        await evaluator.start()

        # Start session before samples flow
        sid = recorder.start_session("smoke-participant")

        # Establish the signal manifest (as a live source would on connect), then stream
        # triggering samples (cognitive_load ≥ 0.4 → the rule fires).
        manifests.update_signal_manifest(json.loads(_MANIFEST_PATH.read_text()))
        await bus.publish(Topics.MANIFEST_UPDATED, manifests.signal_manifest)
        inject_task = asyncio.create_task(_inject_samples())

        # Wait up to 3 s for at least one StatusRequest to reach the mock Unity
        deadline = time.monotonic() + 3.0
        while not received and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        # Stop recording before teardown
        await recorder.stop_session()

    finally:
        if inject_task is not None:
            inject_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await inject_task
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
    store = SqliteStore(data_dir / "vcore.db")
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
            stream_name="sensor.cognitive",
            timestamp=1.0,
            values={"cognitive_load": 0.9, "eeg_alpha_power": 50.0, "affect": "stressed"},
        ),
    )
    await asyncio.sleep(0.05)

    await evaluator.stop()

    assert not fired, f"rule fired despite missing object manifest: {fired}"
