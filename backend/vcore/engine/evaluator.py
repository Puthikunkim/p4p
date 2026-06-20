from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    ActionRequest,
    ConditionGroup,
    ConditionItem,
    Rule,
    SampleEvent,
    StatusRequest,
    TagTarget,
)
from vcore.core.schema import ActiveManifests
from vcore.engine import degradation
from vcore.engine.registry import RuleRegistry

log = logging.getLogger(__name__)

# (rule_id, condition_index) → monotonic time when that condition first became true
_SustainKey = tuple[str, int]


class RuleEvaluator:
    """Evaluates rules against live signal samples and emits StatusRequests.

    Lifecycle:
      1. Call start() — subscribes to the bus.
      2. Samples arrive via Topics.SAMPLE; rules are evaluated on each frame.
      3. Call stop() — unsubscribes.

    Sustain tracking: a condition with sustain_s must remain continuously true
    for that many seconds before it contributes to firing.

    Cooldown: after a rule fires, it is suppressed for cooldown_s seconds.
    """

    def __init__(
        self,
        registry: RuleRegistry,
        bus: EventBus,
        manifests: ActiveManifests,
    ) -> None:
        self._registry = registry
        self._bus = bus
        self._manifests = manifests
        self._latest: dict[str, float | str] = {}
        self._sustain_start: dict[_SustainKey, float] = {}
        self._last_fire: dict[str, float] = {}
        self._disabled: dict[str, str] = {}

    async def start(self) -> None:
        self._bus.subscribe(Topics.SAMPLE, self._on_sample)
        self._bus.subscribe(Topics.MANIFEST_UPDATED, self._on_manifest_change)
        self._bus.subscribe(Topics.OBJECT_STATUS_UPDATED, self._on_manifest_change)
        self._reconcile()

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.SAMPLE, self._on_sample)
        self._bus.unsubscribe(Topics.MANIFEST_UPDATED, self._on_manifest_change)
        self._bus.unsubscribe(Topics.OBJECT_STATUS_UPDATED, self._on_manifest_change)

    # Called by the registry hot-reload path to re-check after rule files change.
    async def on_registry_change(self) -> None:
        self._reconcile()
        await self._bus.publish(Topics.RULES_UPDATED, None)
        await self._bus.publish(
            Topics.WARNING,
            {"source": "evaluator", "message": "rule registry reloaded"},
        )

    # ── bus handlers ──────────────────────────────────────────────────────────

    async def _on_sample(self, event: object) -> None:
        if not isinstance(event, SampleEvent):
            return
        self._latest.update(event.values)
        now = time.monotonic()

        for rule_id, rule in self._registry.rules.items():
            if rule_id in self._disabled:
                continue
            if self._evaluate_group(rule.when, rule_id, now):
                await self._maybe_fire(rule, now)

    async def _on_manifest_change(self, _: object) -> None:
        self._reconcile()
        await self._bus.publish(Topics.RULES_UPDATED, None)

    # ── reconciliation ────────────────────────────────────────────────────────

    def _reconcile(self) -> None:
        self._disabled = degradation.reconcile(
            self._registry.rules,
            self._manifests.signal_manifest,
            self._manifests.object_status_manifest,
        )
        if self._disabled:
            log.debug("degradation: %d rule(s) disabled", len(self._disabled))

    # ── evaluation ────────────────────────────────────────────────────────────

    def _evaluate_group(self, group: ConditionGroup, rule_id: str, now: float) -> bool:
        conditions = group.all if group.all is not None else (group.any or [])
        combine = all if group.all is not None else any
        return combine(
            self._evaluate_condition(c, (rule_id, i), now)
            for i, c in enumerate(conditions)
        )

    def _evaluate_condition(self, cond: ConditionItem, key: _SustainKey, now: float) -> bool:
        value = self._latest.get(cond.signal)
        if value is None:
            self._sustain_start.pop(key, None)
            return False

        passes = self._apply_op(cond, value)

        if not passes:
            self._sustain_start.pop(key, None)
            return False

        sustain = cond.sustain_s or 0.0
        if sustain > 0:
            if key not in self._sustain_start:
                self._sustain_start[key] = now
            return (now - self._sustain_start[key]) >= sustain

        # No sustain — clear any stale start time and return true
        self._sustain_start.pop(key, None)
        return True

    def _apply_op(self, cond: ConditionItem, value: float | str) -> bool:
        op = cond.op
        try:
            fval = float(value)
        except (TypeError, ValueError):
            fval = 0.0  # categorical — numeric ops always false, == / != handled below

        if op == ">":
            return fval > (cond.threshold or 0.0)
        if op == ">=":
            return fval >= (cond.threshold or 0.0)
        if op == "<":
            return fval < (cond.threshold or 0.0)
        if op == "<=":
            return fval <= (cond.threshold or 0.0)
        if op == "==":
            return str(value) == str(cond.value if cond.value is not None else cond.threshold)
        if op == "!=":
            return str(value) != str(cond.value if cond.value is not None else cond.threshold)
        if op == "between":
            return (cond.low or 0.0) <= fval <= (cond.high or 0.0)
        return False

    # ── firing ────────────────────────────────────────────────────────────────

    async def _maybe_fire(self, rule: Rule, now: float) -> None:
        cooldown = rule.then.cooldown_s or 0.0
        last = self._last_fire.get(rule.id, 0.0)
        if now - last < cooldown:
            return
        self._last_fire[rule.id] = now
        await self._emit(rule)

    async def _emit(self, rule: Rule) -> None:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        req: StatusRequest | ActionRequest
        if rule.then.action is not None:
            act = rule.then.action
            req = ActionRequest(
                schema_version="1.0.0",
                intent_id=str(uuid.uuid4()),
                timestamp=ts,
                action=act.action,
                target=act.target,
                source_rule=rule.id,
                source="engine",
            )
            log.info("engine: rule %r fired → action %s on %s", rule.id, act.action, _target_label(act.target))
        else:
            assert rule.then.set is not None  # ThenClause guarantees exactly one
            req = StatusRequest(
                schema_version="1.0.0",
                intent_id=str(uuid.uuid4()),
                timestamp=ts,
                target=rule.then.set.target,
                status=rule.then.set.status,
                value=rule.then.set.value,
                source_rule=rule.id,
                source="engine",
            )
            log.info("engine: rule %r fired → %s=%s on %s", rule.id, req.status, req.value, _target_label(req.target))
        await self._bus.publish(Topics.RULE_FIRED, req)

    # ── public read ───────────────────────────────────────────────────────────

    @property
    def disabled_rules(self) -> dict[str, str]:
        """rule_id → reason for all currently disabled rules."""
        return dict(self._disabled)


def _target_label(target: Any) -> str:
    if target is None:
        return "scene"
    if isinstance(target, TagTarget):
        return f"tag:{target.tag}"
    return f"id:{target.id}"
