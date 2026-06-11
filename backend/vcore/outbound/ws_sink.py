from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

import websockets

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    IdTarget,
    LinkStatusEvent,
    StatusRequest,
    TagTarget,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests
from vcore.outbound.base import ActionSink

log = logging.getLogger(__name__)


class WsSink(ActionSink):
    """WebSocket server that the Unity runtime connects to.

    Protocol (one connection at a time):
      1. Unity connects to ws://<host>:<port>.
      2. Unity sends the Object-Status Manifest as a JSON string.
      3. V-CORE validates + stores the manifest and publishes OBJECT_STATUS_UPDATED.
      4. V-CORE sends a StatusRequest JSON string whenever the rule engine fires.
      5. Unity closes the connection to signal a scene change or shutdown.

    Link status events are published on connect, disconnect, and manifest failure.
    Incoming StatusRequests are validated against the active manifest before delivery;
    unresolvable targets or out-of-range values are dropped with a WARNING.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        bus: EventBus,
        manifests: ActiveManifests,
    ) -> None:
        self._host = host
        self._port = port
        self._bus = bus
        self._manifests = manifests
        self._conn: Any = None
        self._server: Any = None
        self._serve_task: asyncio.Task[None] | None = None
        self._ready: asyncio.Event = asyncio.Event()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._ready = asyncio.Event()
        self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._serve_task = asyncio.create_task(self._serve())
        await self._ready.wait()

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.RULE_FIRED, self._on_rule_fired)
        if self._serve_task and not self._serve_task.done():
            self._serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._serve_task
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    @property
    def bound_port(self) -> int:
        """Actual port the server is listening on (valid after start())."""
        if self._server is None:
            raise RuntimeError("server not started")
        return int(self._server.sockets[0].getsockname()[1])

    # ── server loop ───────────────────────────────────────────────────────────

    async def _serve(self) -> None:
        async with websockets.serve(self.handle_connection, self._host, self._port) as server:
            self._server = server
            self._ready.set()
            log.info("ws_sink: listening on ws://%s:%d", self._host, self._port)
            await asyncio.Future()  # run until cancelled

    # ── connection handler ────────────────────────────────────────────────────

    async def handle_connection(self, ws: Any) -> None:
        """Handle one Unity WebSocket connection.

        `ws` must expose: ``recv() -> str``, ``send(str) -> None``, ``remote_address``.
        Compatible with both the *websockets* library and a thin FastAPI adapter.
        """
        log.info("ws_sink: Unity connected from %s", ws.remote_address)
        self._conn = ws
        await self._bus.publish(
            Topics.LINK_STATUS,
            LinkStatusEvent(link="unity-ws", state="up"),
        )
        try:
            raw = await ws.recv()
            payload: dict[str, Any] = json.loads(raw)
            result = self._manifests.update_object_status_manifest(payload)
            if result.warning:
                await self._bus.publish(
                    Topics.WARNING,
                    WarningEvent(source="ws_sink", message=result.warning),
                )
            if not result.accepted:
                log.error("ws_sink: manifest refused — %s", result.warning)
                await self._bus.publish(
                    Topics.LINK_STATUS,
                    LinkStatusEvent(link="unity-ws", state="down", detail="manifest refused"),
                )
                return
            await self._bus.publish(
                Topics.OBJECT_STATUS_UPDATED,
                self._manifests.object_status_manifest,
            )
            log.info("ws_sink: object-status manifest accepted")

            # Keep alive: read until Unity closes the connection.
            while True:
                try:
                    await ws.recv()
                except Exception:
                    break

        except Exception as exc:
            log.debug("ws_sink: connection closed: %s", type(exc).__name__)
        finally:
            self._conn = None
            log.info("ws_sink: Unity disconnected")
            await self._bus.publish(
                Topics.LINK_STATUS,
                LinkStatusEvent(link="unity-ws", state="down"),
            )

    # ── bus handler ───────────────────────────────────────────────────────────

    async def _on_rule_fired(self, event: object) -> None:
        if not isinstance(event, StatusRequest):
            return
        ws = self._conn
        if ws is None:
            log.debug("ws_sink: no Unity connection — dropping StatusRequest for rule %r", event.source_rule)
            return

        reason = _validate_request(self._manifests.object_status_manifest, event)
        if reason:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(
                    source="ws_sink",
                    message=f"StatusRequest dropped (rule {event.source_rule!r}): {reason}",
                ),
            )
            log.warning("ws_sink: dropped — %s", reason)
            return

        try:
            await ws.send(event.model_dump_json())
        except Exception:
            log.warning("ws_sink: connection closed while sending StatusRequest")


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
