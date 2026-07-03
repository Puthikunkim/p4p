"""Phase 2 tests — event bus and active-manifest registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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
    await bus.publish(Topics.LINK_STATUS, {"link": "sensor-pipeline", "state": "up"})


# ── ActiveManifests ───────────────────────────────────────────────────────────

def test_signal_manifest_accepted_on_valid_payload() -> None:
    m = ActiveManifests()
    payload = _load("signal_schema.valid.json")
    result = m.update_signal_manifest(payload)
    assert result.accepted
    # signal_manifest returns a fresh union dict (one stream here) equal to the input.
    assert m.signal_manifest == payload


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

    assert m.signal_manifest == good  # untouched


# ── behavioural channel merge (Unity-declared) ────────────────────────────────

_BEHAVIOUR_CH = [{
    "name": "response_latency", "unit": "s", "type": "scalar",
    "range": {"min": 0, "max": 15},
    "display": {"hint": "stat_card", "label": "Response Latency", "group": "behavioural"},
}]


def test_behaviour_channels_merge_into_signal_manifest() -> None:
    m = ActiveManifests()
    m.update_signal_manifest(_load("signal_schema.valid.json"))
    base_count = len(m.signal_manifest["channels"])
    m.update_behaviour_channels(_BEHAVIOUR_CH)
    names = [c["name"] for c in m.signal_manifest["channels"]]
    assert "response_latency" in names
    assert len(m.signal_manifest["channels"]) == base_count + 1


def test_behaviour_channels_need_a_base_manifest() -> None:
    m = ActiveManifests()
    m.update_behaviour_channels(_BEHAVIOUR_CH)
    assert m.signal_manifest is None  # nothing to merge into yet


def test_behaviour_channels_reject_malformed() -> None:
    m = ActiveManifests()
    m.update_signal_manifest(_load("signal_schema.valid.json"))
    with pytest.raises(ValidationError):
        m.update_behaviour_channels([{"name": "broken"}])  # missing unit/type/display


def test_merged_manifest_keeps_behavioural_rule_enabled() -> None:
    """A rule on a behavioural signal must not be degraded once Unity declares it."""
    from vcore.core.models import Rule
    from vcore.engine import degradation

    rule = Rule.model_validate({
        "id": "behaviour-demo", "schema_version": "1.0.0", "enabled": True,
        "when": {"all": [{"signal": "response_latency", "op": ">=", "threshold": 8}]},
        "then": {"set": {"target": {"tag": "fog"}, "status": "density", "value": "medium"}},
    })
    obj_manifest = _load("object_status_manifest.valid.json")

    m = ActiveManifests()
    m.update_signal_manifest(_load("signal_schema.valid.json"))
    # Before Unity declares it, the signal is unknown → rule disabled.
    disabled_before = degradation.reconcile({rule.id: rule}, m.signal_manifest, obj_manifest)
    assert rule.id in disabled_before
    assert "response_latency" in disabled_before[rule.id]

    # After the merge the signal is known, so the rule is no longer degraded for it.
    m.update_behaviour_channels(_BEHAVIOUR_CH)
    disabled_after = degradation.reconcile({rule.id: rule}, m.signal_manifest, obj_manifest)
    assert rule.id not in disabled_after or "response_latency" not in disabled_after.get(rule.id, "")
