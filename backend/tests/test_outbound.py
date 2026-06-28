"""Phase 5 tests — the WsSink /ws/runtime handler (integration + target-matching unit tests).

WsSink no longer runs its own socket server; the ``/ws/runtime`` route hands it each
connection. These tests drive :meth:`WsSink.handle_connection` directly with an in-memory
fake WebSocket (``FakeWs``) — same protocol coverage, no real socket bind.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    ActionRequest,
    LinkStatusEvent,
    SampleEvent,
    StatusRequest,
    VrContextEvent,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests
from vcore.outbound.ws_sink import WsSink, _validate_action, _validate_request

# ── in-memory fake WebSocket ──────────────────────────────────────────────────

_CLOSE = object()


class _ClientGone(Exception):
    """Raised by FakeWs.recv when the simulated client disconnects."""


class FakeWs:
    """Duck-typed WebSocket driving WsSink.handle_connection without a real socket.

    The test plays the client: ``client_send()`` pushes a frame to the handler;
    ``sent`` collects the frames the handler sends back.
    """

    remote_address = "test:0"

    def __init__(self) -> None:
        self._inbox: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[str] = []

    # server-facing surface (called by handle_connection)
    async def recv(self) -> str:
        item = await self._inbox.get()
        if item is _CLOSE:
            raise _ClientGone
        assert isinstance(item, str)
        return item

    async def send(self, data: str) -> None:
        self.sent.append(data)

    # client-facing helpers (called by the test)
    async def client_send(self, frame: str) -> None:
        await self._inbox.put(frame)

    def disconnect(self) -> None:
        self._inbox.put_nowait(_CLOSE)


@asynccontextmanager
async def _connect(sink: WsSink) -> AsyncIterator[FakeWs]:
    """Open a simulated Unity connection: run handle_connection in the background,
    yield the fake socket, then disconnect and await teardown (the link-down publish)."""
    ws = FakeWs()
    task = asyncio.create_task(sink.handle_connection(ws))
    await asyncio.sleep(0.02)  # let the handler register the connection + publish link-up
    try:
        yield ws
    finally:
        ws.disconnect()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=1.0)


# ── fixtures ──────────────────────────────────────────────────────────────────

OBJECT_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "scene": "test_scene",
    "runtime": "mock",
    "objects": [
        {
            "id": "light-1",
            "tags": ["ambient_light"],
            "statuses": [
                {"name": "brightness", "type": "continuous", "range": {"min": 0, "max": 100}}
            ],
        },
        {
            "id": "fog-1",
            "tags": ["fog"],
            "statuses": [
                {"name": "density", "type": "discrete", "values": ["low", "medium", "high"]}
            ],
        },
    ],
    "abstract_actions": [],
}


def _frame(manifest: dict[str, Any]) -> str:
    """Wrap an object-status manifest in its typed envelope (the wire format)."""
    return json.dumps({"type": "object_status_manifest", "payload": manifest})


_OBJECT_FRAME = _frame(OBJECT_MANIFEST)


def _make_req(
    *,
    tag: str = "ambient_light",
    status: str = "brightness",
    value: float | str = 20.0,
    rule_id: str = "test-rule",
) -> StatusRequest:
    return StatusRequest(
        schema_version="1.0.0",
        intent_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        target={"tag": tag},
        status=status,
        value=value,
        source_rule=rule_id,
        source="engine",
    )


async def _make_sink() -> tuple[WsSink, EventBus, ActiveManifests]:
    bus = EventBus()
    manifests = ActiveManifests()
    sink = WsSink(bus=bus, manifests=manifests)
    await sink.start()
    return sink, bus, manifests


# ── handshake ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handshake_publishes_manifest() -> None:
    sink, bus, manifests = await _make_sink()
    received: list[object] = []
    bus.subscribe(Topics.OBJECT_STATUS_UPDATED, lambda p: received.append(p))

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)

    await sink.stop()

    assert len(received) == 1
    assert manifests.object_status_manifest is not None
    assert manifests.object_status_manifest["scene"] == "test_scene"


CATALOG_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "scene": "(project catalog)",
    "runtime": "catalog",
    "objects": [
        {"id": "door-1", "tags": ["door"],
         "statuses": [{"name": "state", "type": "discrete", "values": ["open", "closed"]}]}
    ],
    "abstract_actions": [
        {"name": "advance_scene", "scope": "scene"},
        {"name": "open", "scope": "object", "id": "door-1", "tags": ["door"]},
    ],
}


@pytest.mark.asyncio
async def test_catalog_publishes_and_stores() -> None:
    sink, bus, manifests = await _make_sink()
    received: list[object] = []
    bus.subscribe(Topics.OBJECT_STATUS_CATALOG_UPDATED, lambda p: received.append(p))

    async with _connect(sink) as ws:
        await ws.client_send(json.dumps({"type": "object_status_catalog", "payload": CATALOG_MANIFEST}))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(received) == 1
    assert manifests.object_status_catalog is not None
    names = [a["name"] for a in manifests.object_status_catalog["abstract_actions"]]
    assert "advance_scene" in names


def _action_req(action: str, target: dict[str, str] | None = None) -> ActionRequest:
    return ActionRequest(
        schema_version="1.0.0", intent_id="x", timestamp="t",
        action=action, target=target, source="engine",
    )


def test_validate_action_scene_ok() -> None:
    manifest = {"objects": [], "abstract_actions": [{"name": "advance_scene", "scope": "scene"}]}
    assert _validate_action(manifest, _action_req("advance_scene")) is None


def test_validate_action_undeclared_rejected() -> None:
    manifest = {"objects": [], "abstract_actions": []}
    assert _validate_action(manifest, _action_req("ghost")) is not None


def test_validate_action_object_by_tag_ok() -> None:
    manifest = {"objects": [], "abstract_actions": [
        {"name": "open", "scope": "object", "id": "door-1", "tags": ["door"]}
    ]}
    assert _validate_action(manifest, _action_req("open", {"tag": "door"})) is None


@pytest.mark.asyncio
async def test_handshake_publishes_link_up_and_down() -> None:
    sink, bus, _ = await _make_sink()
    events: list[LinkStatusEvent] = []

    async def on_link(p: object) -> None:
        if isinstance(p, LinkStatusEvent) and p.link == "unity-ws":
            events.append(p)

    bus.subscribe(Topics.LINK_STATUS, on_link)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.1)
    # connection is now closed
    await asyncio.sleep(0.05)
    await sink.stop()

    states = [e.state for e in events]
    assert "up" in states
    assert "down" in states
    assert states.index("up") < states.index("down")


# ── StatusRequest delivery ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_request_delivered_to_unity() -> None:
    sink, bus, _ = await _make_sink()
    received_by_client: list[dict[str, Any]] = []

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)  # let manifest be processed
        # Fire a StatusRequest on the bus
        req = _make_req(tag="ambient_light", status="brightness", value=30.0)
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.05)
        received_by_client = [json.loads(m) for m in ws.sent]

    await sink.stop()

    assert len(received_by_client) == 1
    assert received_by_client[0]["status"] == "brightness"
    assert received_by_client[0]["value"] == 30.0


@pytest.mark.asyncio
async def test_no_delivery_without_connection() -> None:
    """A RULE_FIRED event while Unity is disconnected must be silently dropped."""
    sink, bus, _ = await _make_sink()
    req = _make_req()
    await bus.publish(Topics.RULE_FIRED, req)
    await asyncio.sleep(0.05)
    await sink.stop()
    # No error — just no delivery


# ── invalid target / out-of-range ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unresolved_tag_emits_warning() -> None:
    sink, bus, _ = await _make_sink()
    warnings: list[WarningEvent] = []

    async def on_warn(p: object) -> None:
        if isinstance(p, WarningEvent):
            warnings.append(p)

    bus.subscribe(Topics.WARNING, on_warn)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        req = _make_req(tag="nonexistent_tag")
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("nonexistent_tag" in w.message for w in warnings)


@pytest.mark.asyncio
async def test_out_of_range_value_emits_warning() -> None:
    sink, bus, _ = await _make_sink()
    warnings: list[WarningEvent] = []
    bus.subscribe(Topics.WARNING, lambda p: warnings.append(p) if isinstance(p, WarningEvent) else None)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        req = _make_req(tag="ambient_light", status="brightness", value=999.0)
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("range" in w.message for w in warnings)


@pytest.mark.asyncio
async def test_invalid_discrete_value_emits_warning() -> None:
    sink, bus, _ = await _make_sink()
    warnings: list[WarningEvent] = []
    bus.subscribe(Topics.WARNING, lambda p: warnings.append(p) if isinstance(p, WarningEvent) else None)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        req = _make_req(tag="fog", status="density", value="extreme")
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("extreme" in w.message for w in warnings)


# ── inbound vr_context (Unity → backend) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_vr_context_message_publishes_event() -> None:
    sink, bus, _ = await _make_sink()
    events: list[VrContextEvent] = []

    async def on_ctx(p: object) -> None:
        if isinstance(p, VrContextEvent):
            events.append(p)

    bus.subscribe(Topics.VR_CONTEXT, on_ctx)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        await ws.client_send(json.dumps({
            "type": "vr_context",
            "payload": {"scene": "Aisle 2", "step": "3 / 8", "items_left": 4, "assist": True},
        }))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(events) == 1
    assert events[0].fields == {"scene": "Aisle 2", "step": "3 / 8", "items_left": 4, "assist": True}


@pytest.mark.asyncio
async def test_vr_context_without_scalar_fields_is_dropped_with_warning() -> None:
    sink, bus, _ = await _make_sink()
    events: list[object] = []
    warnings: list[WarningEvent] = []
    bus.subscribe(Topics.VR_CONTEXT, lambda p: events.append(p))
    bus.subscribe(Topics.WARNING, lambda p: warnings.append(p) if isinstance(p, WarningEvent) else None)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        # Nested object is not a scalar field, so nothing survives → dropped.
        await ws.client_send(json.dumps({"type": "vr_context", "payload": {"nested": {"a": 1}}}))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert events == []
    assert any("vr_context" in w.message for w in warnings)


@pytest.mark.asyncio
async def test_unknown_inbound_type_is_ignored() -> None:
    """A message Unity sends that isn't a known type must not crash the read loop."""
    sink, bus, _ = await _make_sink()
    events: list[object] = []
    bus.subscribe(Topics.VR_CONTEXT, lambda p: events.append(p))

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        await ws.client_send(json.dumps({"type": "something_else", "payload": {"x": 1}}))
        await ws.client_send("not json at all")
        await asyncio.sleep(0.1)
        # Still alive: a following vr_context still gets through.
        await ws.client_send(json.dumps({"type": "vr_context", "payload": {"step": "1"}}))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(events) == 1


@pytest.mark.asyncio
async def test_object_status_manifest_can_be_resent_mid_session() -> None:
    """A re-sent manifest (e.g. on a Unity scene change) replaces the active one."""
    sink, bus, manifests = await _make_sink()
    updates: list[object] = []
    bus.subscribe(Topics.OBJECT_STATUS_UPDATED, lambda p: updates.append(p))

    scene_two = {
        "schema_version": "1.0.0",
        "scene": "scene_two",
        "runtime": "mock",
        "objects": [
            {"id": "door-1", "tags": ["door"],
             "statuses": [{"name": "open", "type": "discrete", "values": ["yes", "no"]}]},
        ],
        "abstract_actions": [],
    }

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)        # initial handshake
        await asyncio.sleep(0.05)
        await ws.client_send(_frame(scene_two))    # scene-change re-send
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(updates) == 2
    assert manifests.object_status_manifest["scene"] == "scene_two"
    assert manifests.object_status_manifest["objects"][0]["id"] == "door-1"


# ── inbound behavioural signals (Unity → backend) ─────────────────────────────

_PHYS_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "stream": {"name": "sensor.cognitive", "source_id": "t", "nominal_srate": 10},
    "channels": [
        {"name": "cognitive_load", "unit": "normalized", "type": "scalar",
         "range": {"min": 0, "max": 1},
         "display": {"hint": "stat_card", "label": "Cognitive Load", "group": "physiological"}},
    ],
}

_BEHAVIOUR_CH = [
    {"name": "task_accuracy", "unit": "%", "type": "scalar", "range": {"min": 0, "max": 100},
     "display": {"hint": "stat_card", "label": "Task Accuracy", "group": "behavioural"}},
]


@pytest.mark.asyncio
async def test_behaviour_manifest_merges_into_signal_manifest() -> None:
    sink, bus, manifests = await _make_sink()
    manifests.update_signal_manifest(_PHYS_MANIFEST)
    updates: list[object] = []
    bus.subscribe(Topics.MANIFEST_UPDATED, lambda p: updates.append(p))

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        await ws.client_send(json.dumps({"type": "behaviour_manifest", "payload": {"channels": _BEHAVIOUR_CH}}))
        await asyncio.sleep(0.1)

    await sink.stop()

    names = [c["name"] for c in manifests.signal_manifest["channels"]]
    assert "task_accuracy" in names
    assert len(updates) >= 1


@pytest.mark.asyncio
async def test_behaviour_sample_emitted_as_signal_event() -> None:
    sink, bus, _ = await _make_sink()
    samples: list[SampleEvent] = []

    async def on_sample(p: object) -> None:
        if isinstance(p, SampleEvent):
            samples.append(p)

    bus.subscribe(Topics.SAMPLE, on_sample)

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        await ws.client_send(json.dumps({"type": "behaviour_sample", "payload": {"response_latency": 9.2, "idle_time": 3}}))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(samples) == 1
    assert samples[0].stream_name == "unity.behaviour"
    assert samples[0].values == {"response_latency": 9.2, "idle_time": 3.0}


@pytest.mark.asyncio
async def test_behaviour_sample_non_numeric_dropped() -> None:
    sink, bus, _ = await _make_sink()
    samples: list[object] = []
    bus.subscribe(Topics.SAMPLE, lambda p: samples.append(p))

    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
        await ws.client_send(json.dumps({"type": "behaviour_sample", "payload": {"response_latency": "slow"}}))
        await asyncio.sleep(0.1)

    await sink.stop()
    assert samples == []


# ── reconnect ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconnect_brings_link_back_up() -> None:
    sink, bus, _ = await _make_sink()
    up_count = 0
    down_count = 0

    async def on_link(p: object) -> None:
        nonlocal up_count, down_count
        if isinstance(p, LinkStatusEvent) and p.link == "unity-ws":
            if p.state == "up":
                up_count += 1
            elif p.state == "down":
                down_count += 1

    bus.subscribe(Topics.LINK_STATUS, on_link)

    # First connection
    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.05)

    # Second connection (reconnect)
    async with _connect(sink) as ws:
        await ws.client_send(_OBJECT_FRAME)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.05)

    await sink.stop()

    assert up_count == 2
    assert down_count >= 2


# ══ _validate_request unit tests ═════════════════════════════════════════════

def test_validate_ok_continuous() -> None:
    req = _make_req(tag="ambient_light", status="brightness", value=50.0)
    assert _validate_request(OBJECT_MANIFEST, req) is None


def test_validate_ok_discrete() -> None:
    req = _make_req(tag="fog", status="density", value="low")
    assert _validate_request(OBJECT_MANIFEST, req) is None


def test_validate_no_manifest() -> None:
    req = _make_req()
    assert _validate_request(None, req) is not None


def test_validate_unresolved_tag() -> None:
    req = _make_req(tag="no_such_tag")
    assert _validate_request(OBJECT_MANIFEST, req) is not None


def test_validate_out_of_range() -> None:
    req = _make_req(tag="ambient_light", status="brightness", value=200.0)
    reason = _validate_request(OBJECT_MANIFEST, req)
    assert reason is not None
    assert "range" in reason


def test_validate_missing_status() -> None:
    req = _make_req(tag="ambient_light", status="nonexistent_status")
    reason = _validate_request(OBJECT_MANIFEST, req)
    assert reason is not None


def test_validate_discrete_bad_value() -> None:
    req = _make_req(tag="fog", status="density", value="extreme")
    reason = _validate_request(OBJECT_MANIFEST, req)
    assert reason is not None
    assert "extreme" in reason


def test_validate_id_target_ok() -> None:
    req = StatusRequest(
        schema_version="1.0.0",
        intent_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        target={"id": "light-1"},
        status="brightness",
        value=50.0,
        source="engine",
    )
    assert _validate_request(OBJECT_MANIFEST, req) is None


def test_validate_id_target_missing() -> None:
    req = StatusRequest(
        schema_version="1.0.0",
        intent_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        target={"id": "no-such-id"},
        status="brightness",
        value=50.0,
        source="engine",
    )
    reason = _validate_request(OBJECT_MANIFEST, req)
    assert reason is not None
    assert "no-such-id" in reason
