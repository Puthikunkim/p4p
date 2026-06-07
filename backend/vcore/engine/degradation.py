from __future__ import annotations

from typing import Any

from vcore.core.models import IdTarget, Rule, TagTarget


def reconcile(
    rules: dict[str, Rule],
    signal_manifest: dict[str, Any] | None,
    object_status_manifest: dict[str, Any] | None,
) -> dict[str, str]:
    """Return a mapping of rule_id → disable_reason for every rule that cannot run.

    Rules absent from the returned dict are considered active and evaluable.
    This is called whenever the signal manifest, object-status manifest, or the
    rule registry changes.
    """
    disabled: dict[str, str] = {}

    known_signals: set[str] = set()
    if signal_manifest:
        known_signals = {ch["name"] for ch in signal_manifest.get("channels", [])}

    for rule_id, rule in rules.items():
        if not rule.enabled:
            disabled[rule_id] = "rule.enabled is false"
            continue

        # ── check when conditions reference known signals ─────────────────
        conditions = rule.when.all or rule.when.any or []
        missing = [c.signal for c in conditions if c.signal not in known_signals]
        if missing:
            disabled[rule_id] = f"unknown signal(s): {', '.join(missing)}"
            continue

        # ── check then.set target + status + value ────────────────────────
        reason = _check_then(rule, object_status_manifest)
        if reason:
            disabled[rule_id] = reason

    return disabled


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_then(rule: Rule, manifest: dict[str, Any] | None) -> str | None:
    """Return a disable reason if the rule's then.set cannot be resolved, else None."""
    if manifest is None:
        return "no object-status manifest received yet"

    set_action = rule.then.set
    target = set_action.target
    status_name = set_action.status
    value = set_action.value

    # Find matching objects
    objects: list[dict[str, Any]] = manifest.get("objects", [])
    matched = _match_objects(target, objects)

    if not matched:
        label = f"tag={target.tag}" if isinstance(target, TagTarget) else f"id={target.id}"
        return f"no object matches {label}"

    # Check the status exists on at least one matched object and the value is valid
    for obj in matched:
        for status in obj.get("statuses", []):
            if status["name"] != status_name:
                continue
            reason = _check_value(status, value)
            if reason is None:
                return None  # at least one object accepts this status+value
            return reason  # wrong value for this status

    return f"status '{status_name}' not found on matched object(s)"


def _match_objects(target: TagTarget | IdTarget, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(target, TagTarget):
        return [o for o in objects if target.tag in o.get("tags", [])]
    return [o for o in objects if o.get("id") == target.id]


def _check_value(status: dict[str, Any], value: float | str) -> str | None:
    """Return a reason string if value is invalid for this status, else None."""
    if status["type"] == "discrete":
        allowed: list[str] = status.get("values", [])
        if value not in allowed:
            return f"value {value!r} not in discrete values {allowed}"
    else:  # continuous
        rng = status.get("range", {})
        lo, hi = rng.get("min", float("-inf")), rng.get("max", float("inf"))
        try:
            fval = float(value)
        except (TypeError, ValueError):
            return f"value {value!r} is not numeric for continuous status"
        if not (lo <= fval <= hi):
            return f"value {fval} out of range [{lo}, {hi}]"
    return None
