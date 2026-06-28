"""Phase 8 — graceful-degradation integration tests.

These tests exercise multiple components wired together (bus + evaluator +
degradation + registry + manifests) to confirm that every failure-mode row
from the architecture document behaves correctly end-to-end, not just at the
unit level.

Failure modes covered
---------------------
1.  Rule references absent signal          → disabled + no fire
2.  Rule re-enabled when manifest arrives  → fires after reconciliation
3.  No object-status manifest              → all rules disabled + no fire
4.  Object-status manifest arrival         → disabled rules re-enabled + fire
5.  Malformed rule file                    → bad rule skipped, good rule fires
6.  enabled=false rule                     → skipped, other rules unaffected
7.  Signal version skew WARN               → manifest accepted + warning on bus
8.  Signal version skew REFUSE             → manifest rejected, old manifest kept
9.  Object-status version skew WARN        → manifest accepted + warning on bus
10. Object-status version skew REFUSE      → manifest rejected
11. Stale signal                           → evaluator does not fire after silence
12. Unity WS disconnected                  → StatusRequests dropped silently, no crash
13. Link status events reach dashboard WS  → bridge forwards LINK_STATUS to browser
14. Stale events reach dashboard WS        → bridge forwards STALE to browser
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    LinkStatusEvent,
    SampleEvent,
    StaleEvent,
    StatusRequest,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests
from vcore.engine import degradation
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry

# ── shared test data ──────────────────────────────────────────────────────────

_SIGNAL_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "stream": {"name": "test.stream", "source_id": "s1", "nominal_srate": 10},
    "channels": [
        {
            "name": "cognitive_load",
            "unit": "normalized",
            "type": "scalar",
            "range": {"min": 0, "max": 1},
            "display": {"hint": "stat_card", "label": "CL", "precision": 2},
        }
    ],
}

_OBJECT_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "scene": "test",
    "runtime": "mock",
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


def _rule_yaml(
    rule_id: str = "r1",
    signal: str = "cognitive_load",
    threshold: float = 0.5,
    enabled: bool = True,
) -> str:
    return yaml.dump(
        {
            "id": rule_id,
            "schema_version": "1.0.0",
            "description": "test",
            "enabled": enabled,
            "when": {"all": [{"signal": signal, "op": ">=", "threshold": threshold}]},
            "then": {
                "set": {"target": {"tag": "ambient_light"}, "status": "brightness", "value": 50}
            },
        }
    )


def _sample(value: float = 1.0, stream: str = "test.stream") -> SampleEvent:
    return SampleEvent(stream_name=stream, timestamp=0.0, values={"cognitive_load": value})


# ── helper to wire up evaluator with both manifests ───────────────────────────

async def _make_evaluator(
    tmp_path: Path,
    *,
    rule_ids: list[str] | None = None,
    with_signal_manifest: bool = True,
    with_object_manifest: bool = True,
    signals: list[str] | None = None,
) -> tuple[EventBus, ActiveManifests, RuleEvaluator, RuleRegistry]:
    rule_ids = rule_ids or ["r1"]
    signals = signals or ["cognitive_load"]
    bus = EventBus()
    manifests = ActiveManifests()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    for rid in rule_ids:
        sig = signals[0] if len(signals) == 1 else signals[rule_ids.index(rid)]
        (rules_dir / f"{rid}.yaml").write_text(_rule_yaml(rid, signal=sig))

    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)

    if with_signal_manifest:
        manifests.update_signal_manifest(_SIGNAL_MANIFEST)
    if with_object_manifest:
        manifests.update_object_status_manifest(_OBJECT_MANIFEST)

    await evaluator.start()
    return bus, manifests, evaluator, registry


# ── 1. Rule references absent signal → disabled + no fire ─────────────────────

@pytest.mark.asyncio
async def test_absent_signal_rule_does_not_fire(tmp_path: Path) -> None:
    bus, manifests, evaluator, _ = await _make_evaluator(
        tmp_path,
        with_signal_manifest=False,  # no manifest → signal unknown
        with_object_manifest=True,
    )
    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)

    # No signal manifest → rule should be disabled
    assert "r1" in evaluator.disabled_rules

    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 0

    await evaluator.stop()


# ── 2. Rule re-enabled when signal manifest arrives ───────────────────────────

@pytest.mark.asyncio
async def test_rule_re_enabled_after_signal_manifest_arrives(tmp_path: Path) -> None:
    bus, manifests, evaluator, _ = await _make_evaluator(
        tmp_path,
        with_signal_manifest=False,
        with_object_manifest=True,
    )
    assert "r1" in evaluator.disabled_rules

    # Arrive with the signal manifest
    manifests.update_signal_manifest(_SIGNAL_MANIFEST)
    await bus.publish(Topics.MANIFEST_UPDATED, _SIGNAL_MANIFEST)
    await asyncio.sleep(0)  # let the event loop flush

    assert "r1" not in evaluator.disabled_rules

    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)
    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 1

    await evaluator.stop()


# ── 3. No object-status manifest → all rules disabled ─────────────────────────

@pytest.mark.asyncio
async def test_no_object_manifest_disables_all_rules(tmp_path: Path) -> None:
    bus, manifests, evaluator, _ = await _make_evaluator(
        tmp_path,
        with_signal_manifest=True,
        with_object_manifest=False,
    )
    assert "r1" in evaluator.disabled_rules
    reason = evaluator.disabled_rules["r1"]
    assert "manifest" in reason.lower()

    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)
    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 0

    await evaluator.stop()


# ── 4. Object-status manifest arrival re-enables rules ───────────────────────

@pytest.mark.asyncio
async def test_rule_re_enabled_after_object_manifest_arrives(tmp_path: Path) -> None:
    bus, manifests, evaluator, _ = await _make_evaluator(
        tmp_path,
        with_signal_manifest=True,
        with_object_manifest=False,
    )
    assert "r1" in evaluator.disabled_rules

    manifests.update_object_status_manifest(_OBJECT_MANIFEST)
    await bus.publish(Topics.OBJECT_STATUS_UPDATED, _OBJECT_MANIFEST)
    await asyncio.sleep(0)

    assert "r1" not in evaluator.disabled_rules

    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)
    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 1

    await evaluator.stop()


# ── 5. Malformed rule file → bad rule skipped, good rule fires ────────────────

@pytest.mark.asyncio
async def test_malformed_rule_skipped_good_rule_fires(tmp_path: Path) -> None:
    bus = EventBus()
    manifests = ActiveManifests()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    (rules_dir / "good.yaml").write_text(_rule_yaml("good"))
    (rules_dir / "bad.yaml").write_text("this: is: not: valid: yaml: [[[")

    registry = RuleRegistry(rules_dir)
    registry.load_all()

    assert "good" in registry.rules
    assert "bad" not in registry.rules  # malformed file silently skipped

    manifests.update_signal_manifest(_SIGNAL_MANIFEST)
    manifests.update_object_status_manifest(_OBJECT_MANIFEST)

    evaluator = RuleEvaluator(registry, bus, manifests)
    await evaluator.start()

    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)
    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 1
    assert fired[0].source_rule == "good"

    await evaluator.stop()


# ── 6. enabled=false → rule never fires ──────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_rule_never_fires(tmp_path: Path) -> None:
    bus = EventBus()
    manifests = ActiveManifests()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    (rules_dir / "off.yaml").write_text(_rule_yaml("off", enabled=False))
    (rules_dir / "on.yaml").write_text(_rule_yaml("on", enabled=True))

    registry = RuleRegistry(rules_dir)
    registry.load_all()
    manifests.update_signal_manifest(_SIGNAL_MANIFEST)
    manifests.update_object_status_manifest(_OBJECT_MANIFEST)

    evaluator = RuleEvaluator(registry, bus, manifests)
    await evaluator.start()

    assert "off" in evaluator.disabled_rules
    assert "on" not in evaluator.disabled_rules

    fired_ids: list[str] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest) and e.source_rule:
            fired_ids.append(e.source_rule)

    bus.subscribe(Topics.RULE_FIRED, _collect)
    await bus.publish(Topics.SAMPLE, _sample(1.0))

    assert "off" not in fired_ids
    assert "on" in fired_ids

    await evaluator.stop()


# ── 7. Signal version skew WARN → accepted + warning on bus ──────────────────

@pytest.mark.asyncio
async def test_signal_version_warn_accepted_and_warning_published() -> None:
    bus = EventBus()
    manifests = ActiveManifests()

    warnings: list[WarningEvent] = []

    async def _collect(e: object) -> None:
        if isinstance(e, WarningEvent):
            warnings.append(e)

    bus.subscribe(Topics.WARNING, _collect)

    minor_bump = {**_SIGNAL_MANIFEST, "schema_version": "1.1.0"}
    result = manifests.update_signal_manifest(minor_bump)

    assert result.accepted
    assert result.warning is not None
    assert "skew" in result.warning.lower() or "minor" in result.warning.lower()
    assert manifests.signal_manifest is not None

    if result.warning:
        await bus.publish(Topics.WARNING, WarningEvent(source="test", message=result.warning))

    assert len(warnings) == 1
    assert "1.1.0" in warnings[0].message


# ── 8. Signal version skew REFUSE → rejected, old manifest kept ───────────────

def test_signal_version_refuse_keeps_old_manifest() -> None:
    manifests = ActiveManifests()
    manifests.update_signal_manifest(_SIGNAL_MANIFEST)
    old = manifests.signal_manifest

    major_bump = {**_SIGNAL_MANIFEST, "schema_version": "2.0.0"}
    result = manifests.update_signal_manifest(major_bump)

    assert not result.accepted
    assert manifests.signal_manifest is old  # pointer unchanged


# ── 9. Object-status version skew WARN → accepted + warning ──────────────────

def test_object_status_version_warn_accepted() -> None:
    manifests = ActiveManifests()
    minor_bump = {**_OBJECT_MANIFEST, "schema_version": "1.1.0"}
    result = manifests.update_object_status_manifest(minor_bump)

    assert result.accepted
    assert result.warning is not None
    assert manifests.object_status_manifest is not None


# ── 10. Object-status version skew REFUSE → rejected ─────────────────────────

def test_object_status_version_refuse_keeps_old_manifest() -> None:
    manifests = ActiveManifests()
    manifests.update_object_status_manifest(_OBJECT_MANIFEST)
    old = manifests.object_status_manifest

    major_bump = {**_OBJECT_MANIFEST, "schema_version": "2.0.0"}
    result = manifests.update_object_status_manifest(major_bump)

    assert not result.accepted
    assert manifests.object_status_manifest is old


# ── 11. Stale signal → evaluator does not fire after silence ──────────────────

@pytest.mark.asyncio
async def test_no_sample_no_fire(tmp_path: Path) -> None:
    """Evaluator only runs on SAMPLE events — silence means no evaluation."""
    bus, manifests, evaluator, _ = await _make_evaluator(tmp_path)

    fired: list[StatusRequest] = []

    async def _collect(e: object) -> None:
        if isinstance(e, StatusRequest):
            fired.append(e)

    bus.subscribe(Topics.RULE_FIRED, _collect)

    # Push one sample above threshold → fires
    await bus.publish(Topics.SAMPLE, _sample(1.0))
    assert len(fired) == 1

    count_before = len(fired)
    # No more samples — even after waiting
    await asyncio.sleep(0.05)
    assert len(fired) == count_before  # no additional fires without new samples

    await evaluator.stop()


# ── 12. Unity WS disconnected → StatusRequests dropped silently ───────────────

@pytest.mark.asyncio
async def test_status_request_dropped_silently_when_unity_disconnected(tmp_path: Path) -> None:
    from vcore.outbound.ws_sink import WsSink

    bus = EventBus()
    manifests = ActiveManifests()
    manifests.update_object_status_manifest(_OBJECT_MANIFEST)

    sink = WsSink(bus=bus, manifests=manifests)
    await sink.start()

    # No Unity connection — publish a StatusRequest directly
    req = StatusRequest(
        schema_version="1.0.0",
        intent_id="test-id",
        timestamp="2026-01-01T00:00:00.000Z",
        target={"tag": "ambient_light"},  # type: ignore[arg-type]
        status="brightness",
        value=50,
        source_rule="r1",
        source="engine",
    )

    warnings: list[object] = []

    async def _collect(e: object) -> None:
        warnings.append(e)

    bus.subscribe(Topics.WARNING, _collect)

    # Must not raise — should be a silent drop
    await bus.publish(Topics.RULE_FIRED, req)
    await asyncio.sleep(0)

    # No warning should be emitted for a simple "no connection" drop
    assert len(warnings) == 0

    await sink.stop()


# ── 13. Link status events reach dashboard WS ─────────────────────────────

@pytest.mark.asyncio
async def test_link_status_forwarded_to_dashboard(tmp_path: Path) -> None:
    """Bridge broadcasts LINK_STATUS events to connected dashboard clients."""
    from vcore.bridge.ws import DashboardBridge
    from vcore.outbound.ws_sink import WsSink

    bus = EventBus()
    manifests = ActiveManifests()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)
    ws_sink = WsSink(bus=bus, manifests=manifests)

    bridge = DashboardBridge(bus, manifests, registry, evaluator, ws_sink)
    await bridge.start()

    class _FakeWS:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send_text(self, text: str) -> None:
            self.sent.append(json.loads(text))

    fake: Any = _FakeWS()
    bridge._clients.add(fake)

    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="down"))

    assert len(fake.sent) == 1
    assert fake.sent[0]["type"] == "link_status"
    assert fake.sent[0]["payload"]["link"] == "sensor-pipeline"
    assert fake.sent[0]["payload"]["state"] == "down"

    await bridge.stop()


# ── 14. Stale events reach dashboard WS (as "warning" type) ──────────────

@pytest.mark.asyncio
async def test_stale_event_forwarded_to_dashboard_as_warning(tmp_path: Path) -> None:
    """Bridge converts STALE events into warning messages for the dashboard."""
    from vcore.bridge.ws import DashboardBridge
    from vcore.outbound.ws_sink import WsSink

    bus = EventBus()
    manifests = ActiveManifests()
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    registry = RuleRegistry(rules_dir)
    registry.load_all()
    evaluator = RuleEvaluator(registry, bus, manifests)
    ws_sink = WsSink(bus=bus, manifests=manifests)

    bridge = DashboardBridge(bus, manifests, registry, evaluator, ws_sink)
    await bridge.start()

    class _FakeWS:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send_text(self, text: str) -> None:
            self.sent.append(json.loads(text))

    fake: Any = _FakeWS()
    bridge._clients.add(fake)

    await bus.publish(Topics.STALE, StaleEvent(stream_name="test.stream", age_s=6.0))

    assert len(fake.sent) == 1
    msg = fake.sent[0]
    assert msg["type"] == "warning"
    assert msg["payload"]["source"] == "stale"
    assert "test.stream" in msg["payload"]["message"]
    assert "6.0" in msg["payload"]["message"]

    await bridge.stop()


# ── degradation.reconcile — multiple disabled rules ───────────────────────────

def test_reconcile_multiple_signals_some_missing() -> None:
    """Rules referencing different signals — only the ones with missing signals disabled."""

    from vcore.core.models import Rule

    def _r(rid: str, signal: str) -> Rule:
        return Rule.model_validate(
            {
                "id": rid,
                "schema_version": "1.0.0",
                "description": "",
                "enabled": True,
                "when": {"all": [{"signal": signal, "op": ">=", "threshold": 0.5}]},
                "then": {
                    "set": {
                        "target": {"tag": "ambient_light"},
                        "status": "brightness",
                        "value": 50,
                    }
                },
            }
        )

    rules = {"r1": _r("r1", "cognitive_load"), "r2": _r("r2", "nonexistent_signal")}
    disabled = degradation.reconcile(rules, _SIGNAL_MANIFEST, _OBJECT_MANIFEST)

    assert "r1" not in disabled
    assert "r2" in disabled
    assert "nonexistent_signal" in disabled["r2"]
