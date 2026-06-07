"""ZMQ PUB/SUB alternative transport for the VR runtime link.

This file is a documented stub. ZMQ is NOT wired by default.

To enable:
  1. pip install pyzmq
  2. Replace ``WsSink`` with ``ZmqSink`` in ``app.py``.
  3. Set ``transport: zmq`` in ``config.yaml``; add ``runtime_zmq_pub`` and
     ``runtime_zmq_pull`` endpoint keys.

Architecture when enabled:
  - V-CORE binds a ZMQ PUB socket; Unity subscribes via NetMQ on the same port.
  - StatusRequests are published on topic ``vcore.status``.
  - Unity sends its Object-Status Manifest on a PUSH→PULL socket at start-up.

Rough implementation sketch::

    import zmq
    import zmq.asyncio

    class ZmqSink(ActionSink):
        def __init__(self, pub_endpoint: str, pull_endpoint: str, *, bus, manifests):
            self._pub_ep = pub_endpoint    # e.g. "tcp://*:9002"
            self._pull_ep = pull_endpoint  # e.g. "tcp://*:9003"
            ...

        async def start(self) -> None:
            ctx = zmq.asyncio.Context()
            self._pub = ctx.socket(zmq.PUB)
            self._pub.bind(self._pub_ep)
            self._pull = ctx.socket(zmq.PULL)
            self._pull.bind(self._pull_ep)
            self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)
            self._recv_task = asyncio.create_task(self._recv_loop())

        async def _recv_loop(self) -> None:
            while True:
                raw = await self._pull.recv_json()
                result = self._manifests.update_object_status_manifest(raw)
                await self._bus.publish(Topics.OBJECT_STATUS_UPDATED, ...)

        async def _on_rule_fired(self, event) -> None:
            if isinstance(event, StatusRequest):
                await self._pub.send_json(
                    event.model_dump(mode="json"),
                    flags=zmq.NOBLOCK,
                )

        async def stop(self) -> None:
            ...
"""
from __future__ import annotations

from vcore.outbound.base import ActionSink


class ZmqSink(ActionSink):
    """ZMQ PUB/SUB alternative to WsSink — not implemented, see module docstring."""

    async def start(self) -> None:
        raise NotImplementedError("ZmqSink is a stub — see module docstring for how to enable")

    async def stop(self) -> None:
        pass
