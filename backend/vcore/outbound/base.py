from __future__ import annotations

from abc import ABC, abstractmethod


class ActionSink(ABC):
    """Outbound adapter that delivers StatusRequests to the VR runtime.

    Implement this to add a new transport (WebSocket, LSL, …).
    The composition root wires one concrete sink to the event bus and
    the ActiveManifests store.

    Lifecycle:
      start() → [receive Object-Status Manifest] → [forward StatusRequests] → stop()

    Each concrete sink is responsible for:
      - Publishing OBJECT_STATUS_UPDATED when the runtime sends its manifest.
      - Publishing LINK_STATUS events (up / down / stale / reconnecting).
      - Dropping + warning when a StatusRequest cannot be resolved against the manifest.
    """

    @abstractmethod
    async def start(self) -> None:
        """Bind / connect and begin processing."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the sink."""
        ...
