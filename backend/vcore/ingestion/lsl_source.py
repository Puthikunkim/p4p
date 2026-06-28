from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import pylsl

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import LinkStatusEvent, SampleEvent, StaleEvent, WarningEvent
from vcore.core.schema import ActiveManifests

log = logging.getLogger(__name__)

LinkState = Literal["up", "down", "stale"]

_RESOLVE_TIMEOUT = 10.0  # seconds to wait for the LSL stream to appear


class LSLSource:
    """Read a live LSL stream from the sensor pipeline and publish samples onto the event bus.

    The Signal Schema manifest is loaded from *manifest_path* (a Contract 1
    JSON sidecar that the sensor pipeline provides alongside its LSL stream). The channel
    order in the manifest must match the LSL stream's channel order.
    """

    def __init__(
        self,
        stream_name: str,
        manifest_path: Path | str,
        *,
        bus: EventBus,
        manifests: ActiveManifests,
        stale_timeout_s: float = 5.0,
        offline_timeout_s: float = 10.0,
        resolve_timeout: float = _RESOLVE_TIMEOUT,
    ) -> None:
        self._stream_name = stream_name
        self._manifest_path = Path(manifest_path)
        self._bus = bus
        self._manifests = manifests
        self._stale_timeout_s = stale_timeout_s
        self._offline_timeout_s = offline_timeout_s
        self._resolve_timeout = resolve_timeout
        self._own_manifest: dict[str, Any] | None = None
        self._inlet: pylsl.StreamInlet | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._last_sample_at: float = 0.0
        self._running = False
        self._is_stale = False
        self._is_offline = False
        self._stale_since: float = 0.0

    @property
    def stream_name(self) -> str:
        return self._stream_name

    @property
    def link_state(self) -> LinkState:
        if self._is_offline:
            return 'down'
        if self._is_stale:
            return 'stale'
        if self._last_sample_at > 0:
            return 'up'
        return 'down'

    async def start(self) -> None:
        raw: dict[str, Any] = json.loads(self._manifest_path.read_text())
        self._own_manifest = raw  # map the LSL stream by *our* channels, not the merged manifest
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

        # Retry resolve until the stream appears or we are stopped.
        streams: list[Any] = []
        while self._running and not streams:
            streams = await loop.run_in_executor(
                None,
                lambda: pylsl.resolve_byprop("name", self._stream_name, timeout=self._resolve_timeout),
            )
            if not streams:
                log.warning("lsl_source: stream %r not found, retrying…", self._stream_name)
                await self._bus.publish(
                    Topics.LINK_STATUS,
                    LinkStatusEvent(link="sensor-pipeline", state="down", detail=f"waiting for '{self._stream_name}'"),
                )
        if not self._running:
            return

        self._inlet = pylsl.StreamInlet(streams[0], processing_flags=pylsl.proc_clocksync)
        manifest = self._own_manifest
        assert manifest is not None

        channel_names = [ch["name"] for ch in manifest["channels"]]
        channel_types = {ch["name"]: ch["type"] for ch in manifest["channels"]}
        channel_categories = {ch["name"]: ch.get("categories", []) for ch in manifest["channels"]}
        stream_id: str = manifest["stream"]["name"]

        log.info("lsl_source: connected to %r", self._stream_name)
        await self._bus.publish(
            Topics.LINK_STATUS,
            LinkStatusEvent(link="sensor-pipeline", state="up"),
        )

        while self._running:
            # pull_sample blocks for up to 0.05 s then returns (None, None)
            sample, timestamp = await loop.run_in_executor(None, lambda: self._inlet.pull_sample(timeout=0.05))  # type: ignore[union-attr]
            if sample is None:
                continue

            values: dict[str, float | str] = {}
            for i, name in enumerate(channel_names):
                raw = sample[i]
                if channel_types[name] == "categorical":
                    cats = channel_categories.get(name, [])
                    idx = int(round(float(raw)))
                    values[name] = cats[idx] if 0 <= idx < len(cats) else str(idx)
                else:
                    values[name] = float(raw)

            self._last_sample_at = time.monotonic()
            await self._bus.publish(
                Topics.SAMPLE,
                SampleEvent(stream_name=stream_id, timestamp=timestamp, values=values),
            )

    async def _watchdog(self) -> None:
        await asyncio.sleep(self._stale_timeout_s)
        while self._running:
            now = time.monotonic()
            age = now - self._last_sample_at
            is_stale = self._last_sample_at > 0 and age > self._stale_timeout_s
            if is_stale and not self._is_stale and not self._is_offline:
                manifest = self._manifests.signal_manifest
                name = manifest["stream"]["name"] if manifest else self._stream_name
                await self._bus.publish(Topics.STALE, StaleEvent(stream_name=name, age_s=age))
                await self._bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="stale"))
                self._is_stale = True
                self._stale_since = now
            elif is_stale and self._is_stale and not self._is_offline and (now - self._stale_since) >= self._offline_timeout_s:
                await self._bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="down", detail="stream went silent"))
                self._is_stale = False
                self._is_offline = True
                self._stale_since = 0.0
            elif not is_stale and self._last_sample_at > 0 and (self._is_stale or self._is_offline):
                await self._bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="up"))
                self._is_stale = False
                self._is_offline = False
                self._stale_since = 0.0
            await asyncio.sleep(0.5)
