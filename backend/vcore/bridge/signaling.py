"""WebRTC signaling broker.

Relays SDP offer/answer and ICE candidates between a single publisher peer
(Unity / mock) and one or more subscriber peers (browser dashboards) over
``/ws/signaling``.  V-CORE never touches media — it is a pure message relay.

Protocol
--------
Each peer sends a single **registration** message first::

    {"role": "publisher"}   # or "subscriber"

The broker replies::

    {"type": "registered", "role": "publisher"|"subscriber", "peer_id": "<uuid>"}

Subscribers receive ``{"type": "publisher-available"}`` whenever the publisher
connects (or immediately on their own connection if one is already present),
and ``{"type": "publisher-gone"}`` when it disconnects.

From that point, messages are relayed unchanged with the sender's ``peer_id``
stamped in.  Both directions work: subscriber → publisher and publisher →
specific subscriber (matched by ``peer_id`` field in the message).
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)


class SignalingBroker:
    """Relay WebRTC signaling messages between one publisher and N subscribers."""

    def __init__(self) -> None:
        self._publisher: WebSocket | None = None
        self._subscribers: dict[str, WebSocket] = {}

    # ── public entry point ────────────────────────────────────────────────────

    async def handle_peer(self, ws: WebSocket) -> None:
        await ws.accept()
        try:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("role") == "publisher":
                await self._run_publisher(ws)
            else:
                await self._run_subscriber(ws)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception:
            log.exception("signaling peer error")

    @property
    def publisher_connected(self) -> bool:
        return self._publisher is not None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # ── publisher handler ─────────────────────────────────────────────────────

    async def _run_publisher(self, ws: WebSocket) -> None:
        peer_id = str(uuid.uuid4())
        self._publisher = ws
        await ws.send_json({"type": "registered", "role": "publisher", "peer_id": peer_id})
        for sub_ws in list(self._subscribers.values()):
            await _safe_send(sub_ws, {"type": "publisher-available"})
        log.info("signaling publisher connected (%s)", peer_id[:8])
        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg.setdefault("from", peer_id)
                target = msg.get("peer_id")
                if target and target in self._subscribers:
                    await _safe_send(self._subscribers[target], msg)
                else:
                    for sub_ws in list(self._subscribers.values()):
                        await _safe_send(sub_ws, msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._publisher = None
            log.info("signaling publisher disconnected")
            for sub_ws in list(self._subscribers.values()):
                await _safe_send(sub_ws, {"type": "publisher-gone"})

    # ── subscriber handler ────────────────────────────────────────────────────

    async def _run_subscriber(self, ws: WebSocket) -> None:
        peer_id = str(uuid.uuid4())
        self._subscribers[peer_id] = ws
        await ws.send_json({"type": "registered", "role": "subscriber", "peer_id": peer_id})
        if self._publisher is not None:
            await ws.send_json({"type": "publisher-available"})
        log.info("signaling subscriber connected (%s)", peer_id[:8])
        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg.setdefault("peer_id", peer_id)
                if self._publisher is not None:
                    await _safe_send(self._publisher, msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._subscribers.pop(peer_id, None)
            log.info("signaling subscriber disconnected (%s)", peer_id[:8])


async def _safe_send(ws: WebSocket, payload: dict) -> None:  # type: ignore[type-arg]
    try:
        await ws.send_json(payload)
    except Exception:
        pass
