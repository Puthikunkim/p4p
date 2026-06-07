"""Phase 5 tests — outbound WsSink (integration + target-matching unit tests)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import websockets

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import LinkStatusEvent, StatusRequest, WarningEvent
from vcore.core.schema import ActiveManifests
from vcore.outbound.ws_sink import WsSink, _validate_request

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
    sink = WsSink("localhost", 0, bus=bus, manifests=manifests)
    await sink.start()
    return sink, bus, manifests


# ── handshake ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handshake_publishes_manifest() -> None:
    sink, bus, manifests = await _make_sink()
    port = sink.bound_port
    received: list[object] = []
    bus.subscribe(Topics.OBJECT_STATUS_UPDATED, lambda p: received.append(p))

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.1)

    await sink.stop()

    assert len(received) == 1
    assert manifests.object_status_manifest is not None
    assert manifests.object_status_manifest["scene"] == "test_scene"


@pytest.mark.asyncio
async def test_handshake_publishes_link_up_and_down() -> None:
    sink, bus, _ = await _make_sink()
    port = sink.bound_port
    events: list[LinkStatusEvent] = []

    async def on_link(p: object) -> None:
        if isinstance(p, LinkStatusEvent) and p.link == "unity-ws":
            events.append(p)

    bus.subscribe(Topics.LINK_STATUS, on_link)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.1)
    # connection is now closed
    await asyncio.sleep(0.1)
    await sink.stop()

    states = [e.state for e in events]
    assert "up" in states
    assert "down" in states
    assert states.index("up") < states.index("down")


# ── StatusRequest delivery ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_request_delivered_to_unity() -> None:
    sink, bus, _ = await _make_sink()
    port = sink.bound_port
    received_by_client: list[dict[str, Any]] = []

    async def client() -> None:
        async with websockets.connect(f"ws://localhost:{port}") as ws:
            await ws.send(json.dumps(OBJECT_MANIFEST))
            await asyncio.sleep(0.05)  # let manifest be processed
            # Fire a StatusRequest on the bus
            req = _make_req(tag="ambient_light", status="brightness", value=30.0)
            await bus.publish(Topics.RULE_FIRED, req)
            # Read the forwarded message
            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
            received_by_client.append(json.loads(msg))

    await client()
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
    port = sink.bound_port
    warnings: list[WarningEvent] = []

    async def on_warn(p: object) -> None:
        if isinstance(p, WarningEvent):
            warnings.append(p)

    bus.subscribe(Topics.WARNING, on_warn)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.05)
        req = _make_req(tag="nonexistent_tag")
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("nonexistent_tag" in w.message for w in warnings)


@pytest.mark.asyncio
async def test_out_of_range_value_emits_warning() -> None:
    sink, bus, _ = await _make_sink()
    port = sink.bound_port
    warnings: list[WarningEvent] = []
    bus.subscribe(Topics.WARNING, lambda p: warnings.append(p) if isinstance(p, WarningEvent) else None)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.05)
        req = _make_req(tag="ambient_light", status="brightness", value=999.0)
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("range" in w.message for w in warnings)


@pytest.mark.asyncio
async def test_invalid_discrete_value_emits_warning() -> None:
    sink, bus, _ = await _make_sink()
    port = sink.bound_port
    warnings: list[WarningEvent] = []
    bus.subscribe(Topics.WARNING, lambda p: warnings.append(p) if isinstance(p, WarningEvent) else None)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.05)
        req = _make_req(tag="fog", status="density", value="extreme")
        await bus.publish(Topics.RULE_FIRED, req)
        await asyncio.sleep(0.1)

    await sink.stop()

    assert any("extreme" in w.message for w in warnings)


# ── reconnect ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconnect_brings_link_back_up() -> None:
    sink, bus, _ = await _make_sink()
    port = sink.bound_port
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
    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.05)

    # Second connection (reconnect)
    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(OBJECT_MANIFEST))
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
