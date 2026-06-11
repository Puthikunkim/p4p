from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import WebSocket, WebSocketDisconnect

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import SampleEvent
from vcore.core.schema import ActiveManifests
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry
from vcore.ingestion.base import SignalSource
from vcore.outbound.ws_sink import WsSink

log = logging.getLogger(__name__)


class DashboardBridge:
    """Broadcasts bus events to all connected browser dashboard WebSocket clients.

    On each new dashboard connection the current state is pushed immediately
    (signal manifest, object-status manifest, rule list).  Live events are
    forwarded as they arrive on the bus.

    Message envelope sent to the client::

        {"type": "<topic-slug>", "payload": <json-serialisable>}

    Known types: ``signal_manifest``, ``object_status_manifest``, ``sample``,
    ``warning``, ``link_status``, ``rule_list``.
    """

    def __init__(
        self,
        bus: EventBus,
        manifests: ActiveManifests,
        registry: RuleRegistry,
        evaluator: RuleEvaluator,
        ws_sink: WsSink,
        signal_source: SignalSource | None = None,
    ) -> None:
        self._bus = bus
        self._manifests = manifests
        self._registry = registry
        self._evaluator = evaluator
        self._ws_sink = ws_sink
        self._signal_source = signal_source
        self._clients: set[WebSocket] = set()
        self._cached_link_states: dict[str, object] = {}
        self._cached_vr_context: object | None = None

    @property
    def signal_source(self) -> SignalSource | None:
        return self._signal_source

    @signal_source.setter
    def signal_source(self, source: SignalSource) -> None:
        self._signal_source = source

    async def start(self) -> None:
        self._bus.subscribe(Topics.MANIFEST_UPDATED, self._on_manifest)
        self._bus.subscribe(Topics.OBJECT_STATUS_UPDATED, self._on_object_status)
        self._bus.subscribe(Topics.SAMPLE, self._on_sample)
        self._bus.subscribe(Topics.WARNING, self._on_warning)
        self._bus.subscribe(Topics.LINK_STATUS, self._on_link_status)
        self._bus.subscribe(Topics.RULES_UPDATED, self._on_rules_updated)
        self._bus.subscribe(Topics.STALE, self._on_stale)
        self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.subscribe(Topics.VR_CONTEXT, self._on_vr_context)

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.MANIFEST_UPDATED, self._on_manifest)
        self._bus.unsubscribe(Topics.OBJECT_STATUS_UPDATED, self._on_object_status)
        self._bus.unsubscribe(Topics.SAMPLE, self._on_sample)
        self._bus.unsubscribe(Topics.WARNING, self._on_warning)
        self._bus.unsubscribe(Topics.LINK_STATUS, self._on_link_status)
        self._bus.unsubscribe(Topics.RULES_UPDATED, self._on_rules_updated)
        self._bus.unsubscribe(Topics.STALE, self._on_stale)
        self._bus.unsubscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.unsubscribe(Topics.VR_CONTEXT, self._on_vr_context)

    # ── connection handler (called from FastAPI route) ────────────────────────

    async def handle_dashboard(self, ws: WebSocket) -> None:
        from vcore.core.models import LinkStatusEvent
        await ws.accept()
        self._clients.add(ws)
        log.info("bridge: dashboard client connected (%d total)", len(self._clients))
        try:
            # Send the full state snapshot before any incremental link events, so a
            # connecting client always receives the manifests/rule list first.
            await self._push_current_state(ws)
            if len(self._clients) == 1:
                await self._bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="browser-ws", state="up"))
            while True:
                try:
                    await ws.receive_text()  # keep-alive; ignore client messages
                except WebSocketDisconnect:
                    break
        finally:
            self._clients.discard(ws)
            log.info("bridge: dashboard client disconnected (%d total)", len(self._clients))
            if not self._clients:
                await self._bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="browser-ws", state="down"))

    async def handle_runtime(self, ws: WebSocket) -> None:
        """Delegate a Unity /ws/runtime connection to WsSink."""
        await ws.accept()
        await self._ws_sink.handle_connection(_FastAPIWsAdapter(ws))

    # ── initial state push ────────────────────────────────────────────────────

    async def _push_current_state(self, ws: WebSocket) -> None:
        from vcore.core.models import LinkStatusEvent
        if self._manifests.signal_manifest is not None:
            await _send(ws, "signal_manifest", self._manifests.signal_manifest)
        if self._manifests.object_status_manifest is not None:
            await _send(ws, "object_status_manifest", self._manifests.object_status_manifest)
        await _send(ws, "rule_list", self._rule_list_payload())
        unity_state: Literal["up", "down"] = "up" if self._ws_sink.is_connected else "down"
        await _send(ws, "link_status", LinkStatusEvent(link="unity-ws", state=unity_state).model_dump(mode="json"))
        if self._signal_source is not None:
            await _send(ws, "link_status", LinkStatusEvent(link="om-lsl", state=self._signal_source.link_state).model_dump(mode="json"))
        for key, payload in self._cached_link_states.items():
            if key == "om-lsl" and self._signal_source is not None:
                continue  # already pushed live state above
            await _send(ws, "link_status", payload)
        if self._cached_vr_context is not None:
            await _send(ws, "vr_context", self._cached_vr_context)

    # ── bus event handlers ────────────────────────────────────────────────────

    async def _on_manifest(self, payload: object) -> None:
        await self._broadcast("signal_manifest", payload)

    async def _on_object_status(self, payload: object) -> None:
        await self._broadcast("object_status_manifest", payload)

    async def _on_sample(self, payload: object) -> None:
        if isinstance(payload, SampleEvent):
            await self._broadcast("sample", payload.model_dump(mode="json"))
        else:
            await self._broadcast("sample", payload)

    async def _on_warning(self, payload: object) -> None:
        from vcore.core.models import WarningEvent  # avoid circular at module level
        if isinstance(payload, WarningEvent):
            await self._broadcast("warning", payload.model_dump(mode="json"))
        else:
            await self._broadcast("warning", payload)

    async def _on_link_status(self, payload: object) -> None:
        from vcore.core.models import LinkStatusEvent
        if isinstance(payload, LinkStatusEvent):
            data = payload.model_dump(mode="json")
            self._cached_link_states[payload.link] = data
            await self._broadcast("link_status", data)
        else:
            await self._broadcast("link_status", payload)

    async def _on_stale(self, payload: object) -> None:
        from vcore.core.models import StaleEvent
        if isinstance(payload, StaleEvent):
            await self._broadcast("warning", {
                "source": "stale",
                "message": f"signal '{payload.stream_name}' stale for {payload.age_s:.1f}s",
            })

    async def _on_rules_updated(self, _: object) -> None:
        await self._broadcast("rule_list", self._rule_list_payload())

    async def _on_rule_fired(self, payload: object) -> None:
        from vcore.core.models import StatusRequest
        if isinstance(payload, StatusRequest):
            await self._broadcast("rule_fired", payload.model_dump(mode="json"))

    async def _on_vr_context(self, payload: object) -> None:
        from vcore.core.models import VrContextEvent
        if isinstance(payload, VrContextEvent):
            data = payload.model_dump(mode="json")
            self._cached_vr_context = data
            await self._broadcast("vr_context", data)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _rule_list_payload(self) -> dict[str, Any]:
        rules = [r.model_dump(mode="json") for r in self._registry.rules.values()]
        return {"rules": rules, "disabled": self._evaluator.disabled_rules}

    async def _broadcast(self, msg_type: str, payload: object) -> None:
        if not self._clients:
            return
        message = json.dumps({"type": msg_type, "payload": payload})
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


async def _send(ws: WebSocket, msg_type: str, payload: Any) -> None:
    await ws.send_text(json.dumps({"type": msg_type, "payload": payload}))


class _FastAPIWsAdapter:
    """Adapts a FastAPI WebSocket to the duck-typed interface WsSink.handle_connection expects."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        client = ws.client
        self.remote_address = f"{client.host}:{client.port}" if client else "unknown"

    async def recv(self) -> str:
        return await self._ws.receive_text()

    async def send(self, data: str) -> None:
        await self._ws.send_text(data)
