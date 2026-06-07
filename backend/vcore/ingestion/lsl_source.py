from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import pylsl

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import SampleEvent, StaleEvent, WarningEvent
from vcore.core.schema import ActiveManifests
from vcore.ingestion.base import SignalSource

log = logging.getLogger(__name__)

_RESOLVE_TIMEOUT = 10.0  # seconds to wait for the LSL stream to appear


class LSLSource(SignalSource):
    """Read a live LSL stream from Om and publish samples onto the event bus.

    The Signal Schema manifest is loaded from *manifest_path* (a Contract 1
    JSON sidecar that Om provides alongside its LSL stream). The channel order
    in the manifest must match the LSL stream's channel order.
    """

    def __init__(
        self,
        stream_name: str,
        manifest_path: Path | str,
        *,
        bus: EventBus,
        manifests: ActiveManifests,
        stale_timeout_s: float = 5.0,
        resolve_timeout: float = _RESOLVE_TIMEOUT,
    ) -> None:
        self._stream_name = stream_name
        self._manifest_path = Path(manifest_path)
        self._bus = bus
        self._manifests = manifests
        self._stale_timeout_s = stale_timeout_s
        self._resolve_timeout = resolve_timeout
        self._inlet: pylsl.StreamInlet | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._last_sample_at: float = 0.0
        self._running = False

    @property
    def stream_name(self) -> str:
        return self._stream_name

    async def start(self) -> None:
        raw: dict[str, Any] = json.loads(self._manifest_path.read_text())
        result = self._manifests.update_signal_manifest(raw)

        if result.warning:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source=self._stream_name, message=result.warning),
            )
        if not result.accepted:
            log.error("lsl_source: manifest refused (%s)", result.warning)
            return

        await self._bus.publish(Topics.MANIFEST_UPDATED, self._manifests.signal_manifest)

        self._running = True
        self._stream_task = asyncio.create_task(self._stream())
        self._watchdog_task = asyncio.create_task(self._watchdog())

    async def stop(self) -> None:
        self._running = False
        for task in (self._stream_task, self._watchdog_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._inlet is not None:
            self._inlet.close_stream()
            self._inlet = None

    # ── private ───────────────────────────────────────────────────────────────

    async def _stream(self) -> None:
        loop = asyncio.get_running_loop()

        # Resolve runs blocking I/O; offload to a thread so the event loop stays alive.
        streams = await loop.run_in_executor(
            None,
            lambda: pylsl.resolve_byprop("name", self._stream_name, timeout=self._resolve_timeout),
        )
        if not streams:
            log.error("lsl_source: stream %r not found after %.1fs", self._stream_name, self._resolve_timeout)
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source=self._stream_name, message=f"LSL stream '{self._stream_name}' not found"),
            )
            return

        self._inlet = pylsl.StreamInlet(streams[0], processing_flags=pylsl.proc_clocksync)
        manifest = self._manifests.signal_manifest
        assert manifest is not None

        channel_names = [ch["name"] for ch in manifest["channels"]]
        channel_types = {ch["name"]: ch["type"] for ch in manifest["channels"]}
        stream_id: str = manifest["stream"]["name"]

        log.info("lsl_source: connected to %r", self._stream_name)

        while self._running:
            # pull_sample blocks for up to 0.05 s then returns (None, None)
            sample, timestamp = await loop.run_in_executor(None, lambda: self._inlet.pull_sample(timeout=0.05))  # type: ignore[union-attr]
            if sample is None:
                continue

            values: dict[str, float | str] = {}
            for i, name in enumerate(channel_names):
                raw = sample[i]
                values[name] = raw if channel_types[name] == "categorical" else float(raw)

            self._last_sample_at = time.monotonic()
            await self._bus.publish(
                Topics.SAMPLE,
                SampleEvent(stream_name=stream_id, timestamp=timestamp, values=values),
            )

    async def _watchdog(self) -> None:
        await asyncio.sleep(self._stale_timeout_s)
        while self._running:
            age = time.monotonic() - self._last_sample_at
            if self._last_sample_at > 0 and age > self._stale_timeout_s:
                manifest = self._manifests.signal_manifest
                name = manifest["stream"]["name"] if manifest else self._stream_name
                await self._bus.publish(
                    Topics.STALE,
                    StaleEvent(stream_name=name, age_s=age),
                )
            await asyncio.sleep(1.0)
