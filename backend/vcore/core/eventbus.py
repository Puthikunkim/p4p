from __future__ import annotations

import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

log = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]]


class Topics:
    MANIFEST_UPDATED = "manifest.updated"
    SAMPLE = "sample"
    OBJECT_STATUS_UPDATED = "object_status.updated"
    RULE_FIRED = "rule.fired"
    WARNING = "warning"
    LINK_STATUS = "link.status"
    STALE = "signal.stale"


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        with contextlib.suppress(ValueError):
            self._subs[topic].remove(handler)

    async def publish(self, topic: str, payload: Any) -> None:
        """Deliver payload to all subscribers of topic in registration order.

        Exceptions in individual handlers are logged and swallowed so one bad
        handler cannot block others or crash the bus.
        """
        for handler in list(self._subs[topic]):
            try:
                await handler(payload)
            except Exception:
                log.exception("handler error on topic %r", topic)


# Module-level singleton — import and use directly.
bus = EventBus()
