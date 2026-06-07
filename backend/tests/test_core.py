"""Phase 2 tests — event bus and active-manifest registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcore.core.eventbus import EventBus, Topics
from vcore.core.schema import ActiveManifests, VersionSkew

EXAMPLES = Path(__file__).parent.parent.parent / "contracts" / "examples"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    data = json.loads((EXAMPLES / name).read_text())
    data.pop("_invalid_reason", None)
    return data


# ── EventBus ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_reaches_all_subscribers() -> None:
    bus = EventBus()
    received: list[str] = []

    async def handler_a(payload: object) -> None:
        received.append(f"a:{payload}")

    async def handler_b(payload: object) -> None:
        received.append(f"b:{payload}")

    bus.subscribe(Topics.SAMPLE, handler_a)
    bus.subscribe(Topics.SAMPLE, handler_b)
    await bus.publish(Topics.SAMPLE, "ping")

    assert received == ["a:ping", "b:ping"]


@pytest.mark.asyncio
async def test_publish_reaches_subscribers_in_registration_order() -> None:
    bus = EventBus()
    order: list[int] = []

    async def first(_: object) -> None:
        order.append(1)

    async def second(_: object) -> None:
        order.append(2)

    async def third(_: object) -> None:
        order.append(3)

    bus.subscribe(Topics.RULE_FIRED, first)
    bus.subscribe(Topics.RULE_FIRED, second)
    bus.subscribe(Topics.RULE_FIRED, third)
    await bus.publish(Topics.RULE_FIRED, {})

    assert order == [1, 2, 3]


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[object] = []

    async def handler(payload: object) -> None:
        received.append(payload)

    bus.subscribe(Topics.WARNING, handler)
    await bus.publish(Topics.WARNING, "first")
    bus.unsubscribe(Topics.WARNING, handler)
    await bus.publish(Topics.WARNING, "second")

    assert received == ["first"]


@pytest.mark.asyncio
async def test_failing_handler_does_not_block_others() -> None:
    bus = EventBus()
    received: list[str] = []

    async def bad(_: object) -> None:
        raise RuntimeError("boom")

    async def good(payload: object) -> None:
        received.append(str(payload))

    bus.subscribe(Topics.SAMPLE, bad)
    bus.subscribe(Topics.SAMPLE, good)
    await bus.publish(Topics.SAMPLE, "ok")

    assert received == ["ok"]


@pytest.mark.asyncio
async def test_publish_to_topic_with_no_subscribers_is_silent() -> None:
    bus = EventBus()
    await bus.publish(Topics.LINK_STATUS, {"link": "om-lsl", "state": "up"})


# ── ActiveManifests ───────────────────────────────────────────────────────────

def test_signal_manifest_accepted_on_valid_payload() -> None:
    m = ActiveManifests()
    payload = _load("signal_schema.valid.json")
    result = m.update_signal_manifest(payload)
    assert result.accepted
    assert m.signal_manifest is payload


def test_object_status_manifest_accepted_on_valid_payload() -> None:
    m = ActiveManifests()
    payload = _load("object_status_manifest.valid.json")
    result = m.update_object_status_manifest(payload)
    assert result.accepted
    assert m.object_status_manifest is payload


def test_manifests_start_as_none() -> None:
    m = ActiveManifests()
    assert m.signal_manifest is None
    assert m.object_status_manifest is None


def test_signal_manifest_refused_on_major_version_skew() -> None:
    m = ActiveManifests()
    payload = {**_load("signal_schema.valid.json"), "schema_version": "2.0.0"}
    result = m.update_signal_manifest(payload)
    assert not result.accepted
    assert result.skew == VersionSkew.REFUSE
    assert m.signal_manifest is None  # previous manifest unchanged


def test_signal_manifest_accepted_with_warning_on_minor_skew() -> None:
    m = ActiveManifests()
    payload = {**_load("signal_schema.valid.json"), "schema_version": "1.1.0"}
    result = m.update_signal_manifest(payload)
    assert result.accepted
    assert result.skew == VersionSkew.WARN
    assert result.warning is not None


def test_object_status_manifest_refused_on_major_version_skew() -> None:
    m = ActiveManifests()
    payload = {**_load("object_status_manifest.valid.json"), "schema_version": "2.0.0"}
    result = m.update_object_status_manifest(payload)
    assert not result.accepted
    assert m.object_status_manifest is None


def test_previous_manifest_kept_on_refuse() -> None:
    m = ActiveManifests()
    good = _load("signal_schema.valid.json")
    m.update_signal_manifest(good)

    bad = {**good, "schema_version": "2.0.0"}
    m.update_signal_manifest(bad)

    assert m.signal_manifest is good  # untouched
