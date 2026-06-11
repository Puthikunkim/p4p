from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

LinkState = Literal["up", "down", "stale"]


class SignalSource(ABC):
    """Abstract base for all signal ingestion adapters.

    Implementations must publish Topics.MANIFEST_UPDATED once the stream
    manifest is known, then Topics.SAMPLE for each arriving frame.
    Stale detection (Topics.STALE) is handled inside each implementation.
    """

    @property
    @abstractmethod
    def stream_name(self) -> str:
        """Human-readable identifier for this source (used in warnings/logs)."""

    @property
    def link_state(self) -> LinkState:
        """Current om-lsl link state: 'up', 'stale', or 'down'."""
        return 'down'

    @abstractmethod
    async def start(self) -> None:
        """Begin streaming. Returns immediately; streaming runs as a background task."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop streaming and cancel any background tasks."""
