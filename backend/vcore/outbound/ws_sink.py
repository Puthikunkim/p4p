from __future__ import annotations

import json
import logging
import time
from typing import Any

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    ActionRequest,
    IdTarget,
    LinkStatusEvent,
    SampleEvent,
    StatusRequest,
    TagTarget,
    VrContextEvent,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests

log = logging.getLogger(__name__)


class WsSink:
    """Handles the Unity runtime's ``/ws/runtime`` WebSocket connection.

    The composition root constructs one instance; the ``/ws/runtime`` route hands
    each connection to :meth:`handle_connection` via a thin adapter.

    Protocol (one connection at a time): every Unity → V-CORE frame is a typed
    JSON envelope ``{"type": ..., "payload": ...}``, routed through _handle_inbound:
      - ``object_status_manifest`` (Contract 3b) — sent on connect and re-sent on
        scene changes; validated, stored, published as OBJECT_STATUS_UPDATED.
      - ``object_status_catalog`` — the project-wide catalog, for authoring rules
        against objects/actions in scenes that aren't loaded yet.
      - ``vr_context`` (Contract 4), ``behaviour_manifest`` / ``behaviour_sample``
        (Contract 5) — routed onto the event bus.
    V-CORE sends a StatusRequest / ActionRequest JSON string whenever the rule engine fires.

    Link status events are published on connect and disconnect. Incoming
    StatusRequests are validated against the active manifest before delivery;
    unresolvable targets or out-of-range values are dropped with a WARNING.
    """

    def __init__(
        self,
        *,
        bus: EventBus,
        manifests: ActiveManifests,
    ) -> None:
        self._bus = bus
        self._manifests = manifests
        self._conn: Any = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.RULE_FIRED, self._on_rule_fired)

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    # ── connection handler ────────────────────────────────────────────────────

    async def handle_connection(self, ws: Any) -> None:
        """Handle one Unity WebSocket connection.

        `ws` must expose: ``recv() -> str``, ``send(str) -> None``, ``remote_address``.
        Satisfied by the ``/ws/runtime`` FastAPI adapter (and the in-memory test fake).
        """
        log.info("ws_sink: Unity connected from %s", ws.remote_address)
        self._conn = ws
        await self._bus.publish(
            Topics.LINK_STATUS,
            LinkStatusEvent(link="unity-ws", state="up"),
        )
        try:
            # Every Unity → V-CORE frame is a typed envelope routed through
            # _handle_inbound. The object-status manifest is the expected first
            # frame but may also be re-sent later (e.g. on a Unity scene change);
            # unknown types are ignored.
            while True:
                msg = await ws.recv()
                await self._handle_inbound(msg)

        except Exception as exc:
            log.debug("ws_sink: connection closed: %s", type(exc).__name__)
        finally:
            self._conn = None
            log.info("ws_sink: Unity disconnected")
            await self._bus.publish(
                Topics.LINK_STATUS,
                LinkStatusEvent(link="unity-ws", state="down"),
            )

    async def _handle_inbound(self, raw: str) -> None:
        """Route one typed Unity frame to the right handler / bus topic."""
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(msg, dict):
            return
        mtype = msg.get("type")
        payload = msg.get("payload")
        if mtype == "object_status_manifest":
            await self._handle_object_status_manifest(payload)
        elif mtype == "object_status_catalog":
            await self._handle_object_status_catalog(payload)
        elif mtype == "vr_context":
            await self._handle_vr_context(payload)
        elif mtype == "behaviour_manifest":
            await self._handle_behaviour_manifest(payload)
        elif mtype == "behaviour_sample":
            await self._handle_behaviour_sample(payload)

    async def _handle_object_status_manifest(self, payload: Any) -> None:
        """Accept the Object-Status Manifest (Contract 3b) — the connection's first
        frame and any later re-send (e.g. a Unity scene change). Replaces the active
        manifest and republishes it so the rule engine and dashboard re-resolve
        targets against the current scene. A refused/invalid manifest is warned and
        the previous one kept; the connection is never dropped for it."""
        if not isinstance(payload, dict):
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message="object_status_manifest dropped: payload must be an object"),
            )
            return
        try:
            result = self._manifests.update_object_status_manifest(payload)
        except Exception as exc:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message=f"object_status_manifest rejected: {exc}"),
            )
            return
        if result.warning:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message=result.warning),
            )
        if not result.accepted:
            return
        await self._bus.publish(
            Topics.OBJECT_STATUS_UPDATED,
            self._manifests.object_status_manifest,
        )
        log.info("ws_sink: object-status manifest accepted")

    async def _handle_object_status_catalog(self, payload: Any) -> None:
        """Accept the project-wide Object-Status Catalog (same shape as the manifest):
        every object/action the project can expose, baked by the Unity editor and sent on
        connect. Used to author rules ahead of time; dispatch + degradation still use the
        live manifest. A bad catalog is warned and ignored; the connection is never dropped."""
        if not isinstance(payload, dict):
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message="object_status_catalog dropped: payload must be an object"),
            )
            return
        try:
            result = self._manifests.update_catalog(payload)
        except Exception as exc:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message=f"object_status_catalog rejected: {exc}"),
            )
            return
        if result.warning:
            await self._bus.publish(Topics.WARNING, WarningEvent(source="ws_sink", message=result.warning))
        if not result.accepted:
            return
        await self._bus.publish(
            Topics.OBJECT_STATUS_CATALOG_UPDATED,
            self._manifests.object_status_catalog,
        )
        log.info("ws_sink: object-status catalog accepted")

    async def _handle_vr_context(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not payload:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message="vr_context dropped: payload must be a non-empty object"),
            )
            return
        # Keep only scalar field values; the dashboard renders whatever survives.
        fields = {k: v for k, v in payload.items() if isinstance(v, (str, int, float, bool))}
        if not fields:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message="vr_context dropped: no scalar fields"),
            )
            return
        await self._bus.publish(Topics.VR_CONTEXT, VrContextEvent(fields=fields))

    async def _handle_behaviour_manifest(self, payload: Any) -> None:
        """Unity declares the behavioural channels it tracks; merge them into the
        active signal manifest so they render, feed rules, and re-enable any
        rules that reference them."""
        channels = payload.get("channels") if isinstance(payload, dict) else None
        if not isinstance(channels, list) or not channels:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message="behaviour_manifest dropped: 'channels' must be a non-empty list"),
            )
            return
        try:
            self._manifests.update_behaviour_channels(channels)
        except Exception as exc:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source="ws_sink", message=f"behaviour_manifest rejected: {exc}"),
            )
            return
        log.info("ws_sink: merged %d behavioural channel(s) from Unity", len(channels))
        await self._bus.publish(Topics.MANIFEST_UPDATED, self._manifests.signal_manifest)

    async def _handle_behaviour_sample(self, payload: Any) -> None:
        """One frame of behavioural metrics from Unity, emitted as a SAMPLE event
        so it flows to the rule engine, dashboard, and recorder like any signal."""
        if not isinstance(payload, dict) or not payload:
            return
        values: dict[str, float | str | None] = {
            k: float(v)
            for k, v in payload.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if not values:
            return
        await self._bus.publish(
            Topics.SAMPLE,
            SampleEvent(stream_name="unity.behaviour", timestamp=_lsl_now(), values=values),
        )

    # ── bus handler ───────────────────────────────────────────────────────────

    async def _on_rule_fired(self, event: object) -> None:
        """Forward a fired rule's output (status change or action invocation) to Unity."""
        manifest = self._manifests.object_status_manifest
        if isinstance(event, StatusRequest):
            kind, reason = "StatusRequest", _validate_request(manifest, event)
        elif isinstance(event, ActionRequest):
            kind, reason = "ActionRequest", _validate_action(manifest, event)
        else:
            return

        ws = self._conn
        if ws is None:
            log.debug("ws_sink: no Unity connection — dropping %s for rule %r", kind, event.source_rule)
            return

        if reason:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(
                    source="ws_sink",
                    message=f"{kind} dropped (rule {event.source_rule!r}): {reason}",
                ),
            )
            log.warning("ws_sink: dropped — %s", reason)
            return

        try:
            # exclude_none so a scene-level action (no target) is sent without a null
            # 'target' key — keeping the frame valid against the contract schema.
            await ws.send(event.model_dump_json(exclude_none=True))
        except Exception:
            log.warning("ws_sink: connection closed while sending %s", kind)


def _lsl_now() -> float:
    """Best-effort LSL clock so Unity samples share the sensor pipeline stream's time domain."""
    try:
        import pylsl
        return float(pylsl.local_clock())
    except Exception:
        return time.time()


# ── target validation ─────────────────────────────────────────────────────────

def _validate_request(
    manifest: dict[str, Any] | None,
    req: StatusRequest,
) -> str | None:
    """Return a rejection reason if req cannot be resolved against manifest, else None."""
    if manifest is None:
        return "no object-status manifest"
    objects: list[dict[str, Any]] = manifest.get("objects", [])
    target = req.target
    if isinstance(target, TagTarget):
        matched = [o for o in objects if target.tag in o.get("tags", [])]
        label = f"tag={target.tag}"
    else:
        assert isinstance(target, IdTarget)
        matched = [o for o in objects if o.get("id") == target.id]
        label = f"id={target.id}"
    if not matched:
        return f"no object matches {label}"
    for obj in matched:
        for status in obj.get("statuses", []):
            if status["name"] != req.status:
                continue
            if status["type"] == "discrete":
                allowed: list[str] = status.get("values", [])
                if req.value not in allowed:
                    return f"value {req.value!r} not in {allowed}"
            else:
                rng = status.get("range", {})
                lo = rng.get("min", float("-inf"))
                hi = rng.get("max", float("inf"))
                try:
                    fv = float(req.value)
                except (TypeError, ValueError):
                    return f"value {req.value!r} is not numeric"
                if not (lo <= fv <= hi):
                    return f"value {req.value} out of range [{lo}, {hi}]"
            return None
    return f"status '{req.status}' not found on matched object(s)"


def _validate_action(
    manifest: dict[str, Any] | None,
    req: ActionRequest,
) -> str | None:
    """Return a rejection reason if the action isn't declared by Unity, else None."""
    if manifest is None:
        return "no object-status manifest"
    declared: list[dict[str, Any]] = manifest.get("abstract_actions", [])
    target = req.target
    for a in declared:
        if a.get("name") != req.action:
            continue
        if target is None:
            if a.get("scope") == "scene":
                return None
        elif isinstance(target, TagTarget):
            if a.get("scope") == "object" and target.tag in a.get("tags", []):
                return None
        elif a.get("scope") == "object" and a.get("id") == target.id:
            return None
    if target is None:
        return f"scene action '{req.action}' not declared"
    label = f"tag={target.tag}" if isinstance(target, TagTarget) else f"id={target.id}"
    return f"action '{req.action}' not declared for {label}"
