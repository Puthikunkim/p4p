"""Phase 4 tests — rule engine (registry, evaluator, degradation)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import Rule, SampleEvent, StatusRequest
from vcore.core.schema import ActiveManifests, validate
from vcore.engine import degradation
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleLoadError, RuleRegistry

# ── helpers ───────────────────────────────────────────────────────────────────

def _rule_dict(
    rule_id: str = "test-rule",
    *,
    op: str = ">=",
    threshold: float = 0.8,
    sustain_s: float | None = None,
    cooldown_s: float | None = None,
    target: dict[str, str] | None = None,
    status: str = "brightness",
    value: Any = 20,
    enabled: bool = True,
    use_any: bool = False,
) -> dict[str, Any]:
    cond: dict[str, Any] = {"signal": "cognitive_load", "op": op, "threshold": threshold}
    if sustain_s is not None:
        cond["sustain_s"] = sustain_s
    when = {"any": [cond]} if use_any else {"all": [cond]}
    then: dict[str, Any] = {
        "set": {
            "target": target or {"tag": "ambient_light"},
            "status": status,
            "value": value,
        }
    }
    if cooldown_s is not None:
        then["cooldown_s"] = cooldown_s
    return {
        "id": rule_id,
        "schema_version": "1.0.0",
        "description": "test",
        "enabled": enabled,
        "when": when,
        "then": then,
    }


def _write_rule(tmp_path: Path, rule_id: str, data: dict[str, Any], fmt: str = "yaml") -> Path:
    p = tmp_path / f"{rule_id}.{fmt}"
    if fmt == "yaml":
        p.write_text(yaml.dump(data))
    else:
        p.write_text(json.dumps(data))
    return p


def _signal_manifest(channels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "stream": {"name": "sensor.cognitive", "source_id": "test", "nominal_srate": 10},
        "channels": channels or [
            {
                "name": "cognitive_load", "unit": "normalized", "type": "scalar",
                "range": {"min": 0, "max": 1},
                "display": {"hint": "stat_card", "label": "Cognitive Load"},
            }
        ],
    }


def _object_manifest(
    obj_id: str = "light-1",
    tags: list[str] | None = None,
    status_name: str = "brightness",
    status_type: str = "continuous",
    values: list[str] | None = None,
    rng: dict[str, float] | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {"name": status_name, "type": status_type}
    if status_type == "discrete":
        status["values"] = values or ["on", "off"]
    else:
        status["range"] = rng or {"min": 0, "max": 100}
    return {
        "schema_version": "1.0.0",
        "scene": "test_scene",
        "runtime": "test",
        "objects": [{"id": obj_id, "tags": tags or ["ambient_light"], "statuses": [status]}],
        "abstract_actions": [],
    }


# ══ Registry ═════════════════════════════════════════════════════════════════

def test_registry_loads_yaml(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r1", _rule_dict("r1"))
    reg = RuleRegistry(tmp_path)
    reg.load_all()
    assert "r1" in reg.rules
    assert not reg.errors


def test_registry_loads_json(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r2", _rule_dict("r2"), fmt="json")
    reg = RuleRegistry(tmp_path)
    reg.load_all()
    assert "r2" in reg.rules


def test_registry_skips_bad_file_keeps_good(tmp_path: Path) -> None:
    _write_rule(tmp_path, "good", _rule_dict("good"))
    (tmp_path / "bad.yaml").write_text("not: valid: yaml: rule")
    reg = RuleRegistry(tmp_path)
    reg.load_all()
    assert "good" in reg.rules
    assert len(reg.errors) == 1
    assert isinstance(reg.errors[0], RuleLoadError)


def test_registry_reload_replaces_rule(tmp_path: Path) -> None:
    p = _write_rule(tmp_path, "r3", _rule_dict("r3", threshold=0.5))
    reg = RuleRegistry(tmp_path)
    reg.load_all()
    assert reg.rules["r3"].when.all[0].threshold == 0.5  # type: ignore[index]

    # Overwrite with updated threshold
    p.write_text(yaml.dump(_rule_dict("r3", threshold=0.9)))
    reg.load_all()
    assert reg.rules["r3"].when.all[0].threshold == 0.9  # type: ignore[index]


@pytest.mark.asyncio
async def test_registry_hot_reload_triggers_callback(tmp_path: Path) -> None:
    reg = RuleRegistry(tmp_path)
    reg.load_all()

    fired: list[int] = []

    async def on_change() -> None:
        fired.append(1)

    loop = asyncio.get_event_loop()
    reg.start_watching(on_change, loop)
    try:
        _write_rule(tmp_path, "new", _rule_dict("new"))
        await asyncio.sleep(0.5)
    finally:
        reg.stop_watching()

    assert len(fired) >= 1


# ══ Degradation ══════════════════════════════════════════════════════════════

def test_degradation_pass_when_manifests_match() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", target={"tag": "ambient_light"}))}
    disabled = degradation.reconcile(rules, _signal_manifest(), _object_manifest())
    assert "r" not in disabled


def test_degradation_disabled_rule_skipped() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", enabled=False))}
    disabled = degradation.reconcile(rules, _signal_manifest(), _object_manifest())
    assert "r" in disabled
    assert "enabled" in disabled["r"]


def test_degradation_missing_signal() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r"))}
    # manifest with NO cognitive_load channel
    sig = _signal_manifest(channels=[
        {
            "name": "eeg_alpha_power", "unit": "uV^2", "type": "timeseries",
            "range": {"min": 0, "max": 100},
            "display": {"hint": "line_chart", "label": "Alpha"},
        }
    ])
    disabled = degradation.reconcile(rules, sig, _object_manifest())
    assert "r" in disabled
    assert "cognitive_load" in disabled["r"]


def test_degradation_no_signal_manifest() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r"))}
    disabled = degradation.reconcile(rules, None, _object_manifest())
    assert "r" in disabled


def test_degradation_unresolved_tag() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", target={"tag": "nonexistent_tag"}))}
    disabled = degradation.reconcile(rules, _signal_manifest(), _object_manifest())
    assert "r" in disabled
    assert "nonexistent_tag" in disabled["r"]


def test_degradation_out_of_range_continuous() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", value=999))}
    disabled = degradation.reconcile(rules, _signal_manifest(), _object_manifest(rng={"min": 0, "max": 100}))
    assert "r" in disabled
    assert "range" in disabled["r"]


def test_degradation_invalid_discrete_value() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", status="mode", value="invalid"))}
    obj = _object_manifest(status_name="mode", status_type="discrete", values=["on", "off"])
    disabled = degradation.reconcile(rules, _signal_manifest(), obj)
    assert "r" in disabled


def test_degradation_no_object_manifest() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r"))}
    disabled = degradation.reconcile(rules, _signal_manifest(), None)
    assert "r" in disabled


def test_degradation_id_target_match() -> None:
    rules = {"r": Rule.model_validate(_rule_dict("r", target={"id": "light-1"}))}
    disabled = degradation.reconcile(rules, _signal_manifest(), _object_manifest(obj_id="light-1"))
    assert "r" not in disabled


# ══ Evaluator — operators ════════════════════════════════════════════════════

def _make_evaluator(tmp_path: Path, rules: list[dict[str, Any]]) -> tuple[RuleEvaluator, EventBus, ActiveManifests, RuleRegistry]:
    for r in rules:
        _write_rule(tmp_path, r["id"], r)
    reg = RuleRegistry(tmp_path)
    reg.load_all()
    bus = EventBus()
    manifests = ActiveManifests()
    manifests.update_signal_manifest(_signal_manifest())
    manifests.update_object_status_manifest(_object_manifest())
    ev = RuleEvaluator(reg, bus, manifests)
    return ev, bus, manifests, reg


async def _fire_sample(bus: EventBus, **values: float | str) -> None:
    await bus.publish(
        Topics.SAMPLE,
        SampleEvent(stream_name="sensor.cognitive", timestamp=0.0, values=dict(values)),
    )


@pytest.mark.asyncio
async def test_evaluator_fires_on_threshold(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.8)])
    await ev.start()
    fired: list[StatusRequest] = []

    async def on_fire(p: object) -> None:
        assert isinstance(p, StatusRequest)
        fired.append(p)

    bus.subscribe(Topics.RULE_FIRED, on_fire)
    await _fire_sample(bus, cognitive_load=0.9)
    assert len(fired) == 1
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_does_not_fire_below_threshold(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.8)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await _fire_sample(bus, cognitive_load=0.5)
    assert not fired
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_between_op(tmp_path: Path) -> None:
    rule = _rule_dict("r")
    rule["when"] = {"all": [{"signal": "cognitive_load", "op": "between", "low": 0.5, "high": 0.9}]}
    ev, bus, _, _ = _make_evaluator(tmp_path, [rule])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await _fire_sample(bus, cognitive_load=0.7)
    assert len(fired) == 1
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_eq_op_categorical(tmp_path: Path) -> None:
    sig = _signal_manifest(channels=[
        {
            "name": "affect", "unit": "category", "type": "categorical",
            "categories": ["calm", "stressed"],
            "display": {"hint": "stat_card", "label": "Affect"},
        }
    ])
    obj = _object_manifest(status_name="brightness")
    rule = _rule_dict("r", target={"tag": "ambient_light"})
    rule["when"] = {"all": [{"signal": "affect", "op": "==", "value": "stressed"}]}

    tmp_path2 = Path(str(tmp_path) + "_eq")
    tmp_path2.mkdir()
    _write_rule(tmp_path2, "r", rule)
    reg = RuleRegistry(tmp_path2)
    reg.load_all()
    bus = EventBus()
    manifests = ActiveManifests()
    manifests.update_signal_manifest(sig)
    manifests.update_object_status_manifest(obj)
    ev = RuleEvaluator(reg, bus, manifests)
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await bus.publish(Topics.SAMPLE, SampleEvent(stream_name="sensor.cognitive", timestamp=0.0, values={"affect": "stressed"}))
    assert len(fired) == 1
    await ev.stop()


# ══ Evaluator — sustain ══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_evaluator_sustain_not_met(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.8, sustain_s=5.0)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await _fire_sample(bus, cognitive_load=0.9)
    assert not fired
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_sustain_met_fires(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.8, sustain_s=0.1)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))

    # First sample starts the sustain clock
    await _fire_sample(bus, cognitive_load=0.9)
    assert not fired

    # Wait for sustain to expire, then send another sample
    await asyncio.sleep(0.15)
    await _fire_sample(bus, cognitive_load=0.9)
    assert len(fired) >= 1
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_sustain_resets_on_dip(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.8, sustain_s=0.1)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))

    await _fire_sample(bus, cognitive_load=0.9)
    await _fire_sample(bus, cognitive_load=0.3)  # dip below threshold — resets
    await asyncio.sleep(0.15)
    await _fire_sample(bus, cognitive_load=0.9)  # restarts clock — should NOT fire yet
    assert not fired
    await ev.stop()


# ══ Evaluator — cooldown ═════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_evaluator_cooldown_suppresses_repeat(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.1, cooldown_s=60.0)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))

    # Pin monotonic to a value well above cooldown_s so the first sample fires
    # (now - default_last=0.0 >= 60) and the immediate second is suppressed
    # (now - now = 0 < 60). Without pinning, a freshly booted container where
    # time.monotonic() < 60 would suppress even the first fire.
    with mock.patch("vcore.engine.evaluator.time") as mt:
        mt.monotonic.return_value = 10_000.0
        await _fire_sample(bus, cognitive_load=0.9)
        await _fire_sample(bus, cognitive_load=0.9)
    assert len(fired) == 1  # second sample suppressed by cooldown
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_fires_again_after_cooldown(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.1, cooldown_s=0.05)])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))

    await _fire_sample(bus, cognitive_load=0.9)
    await asyncio.sleep(0.1)
    await _fire_sample(bus, cognitive_load=0.9)
    assert len(fired) == 2
    await ev.stop()


# ══ Evaluator — boolean composition ═════════════════════════════════════════

@pytest.mark.asyncio
async def test_evaluator_any_fires_if_one_condition_true(tmp_path: Path) -> None:
    rule = _rule_dict("r", use_any=True, op=">=", threshold=0.8)
    ev, bus, _, _ = _make_evaluator(tmp_path, [rule])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await _fire_sample(bus, cognitive_load=0.9)
    assert len(fired) == 1
    await ev.stop()


@pytest.mark.asyncio
async def test_evaluator_all_requires_all_conditions(tmp_path: Path) -> None:
    rule = _rule_dict("r")
    rule["when"] = {
        "all": [
            {"signal": "cognitive_load", "op": ">=", "threshold": 0.8},
            {"signal": "cognitive_load", "op": "<", "threshold": 0.5},  # contradicts first
        ]
    }
    ev, bus, _, _ = _make_evaluator(tmp_path, [rule])
    await ev.start()
    fired: list[object] = []
    bus.subscribe(Topics.RULE_FIRED, lambda p: fired.append(p))
    await _fire_sample(bus, cognitive_load=0.9)
    assert not fired
    await ev.stop()


# ══ StatusRequest schema validity ════════════════════════════════════════════

@pytest.mark.asyncio
async def test_emitted_status_request_validates_against_contract(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.1)])
    await ev.start()
    fired: list[StatusRequest] = []

    async def on_fire(p: object) -> None:
        assert isinstance(p, StatusRequest)
        fired.append(p)

    bus.subscribe(Topics.RULE_FIRED, on_fire)
    await _fire_sample(bus, cognitive_load=0.9)
    await ev.stop()

    assert len(fired) == 1
    req = fired[0]
    # Validate the emitted payload against the contract JSON Schema
    payload = req.model_dump(mode="json")
    validate(payload, "status_request")  # raises on failure


@pytest.mark.asyncio
async def test_emitted_status_request_has_engine_source(tmp_path: Path) -> None:
    ev, bus, _, _ = _make_evaluator(tmp_path, [_rule_dict("r", op=">=", threshold=0.1)])
    await ev.start()
    fired: list[StatusRequest] = []

    async def on_fire(p: object) -> None:
        assert isinstance(p, StatusRequest)
        fired.append(p)

    bus.subscribe(Topics.RULE_FIRED, on_fire)
    await _fire_sample(bus, cognitive_load=0.9)
    await ev.stop()

    assert fired[0].source == "engine"
    assert fired[0].source_rule == "r"
