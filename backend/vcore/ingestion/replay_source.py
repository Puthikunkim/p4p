from __future__ import annotations

import asyncio
import contextlib
import csv
import itertools
import json
import logging
import time
from pathlib import Path
from typing import Any

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import SampleEvent, StaleEvent, WarningEvent
from vcore.core.schema import ActiveManifests
from vcore.ingestion.base import SignalSource

log = logging.getLogger(__name__)


class ReplaySource(SignalSource):
    """Replay a CSV fixture at the stream's nominal sample rate.

    Expects two files:
      - *manifest_path*: a Signal Schema JSON (Contract 1)
      - *csv_path*:      one row per sample, columns = channel names

    Rows are cycled indefinitely so tests can run as long as needed.
    Stale detection fires if the streaming task is cancelled or falls behind.
    """

    def __init__(
        self,
        manifest_path: Path | str,
        csv_path: Path | str,
        *,
        bus: EventBus,
        manifests: ActiveManifests,
        stale_timeout_s: float = 5.0,
        loop: bool = True,
    ) -> None:
        self._manifest_path = Path(manifest_path)
        self._csv_path = Path(csv_path)
        self._bus = bus
        self._manifests = manifests
        self._stale_timeout_s = stale_timeout_s
        self._loop = loop
        self._stream_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._last_sample_at: float = 0.0
        self._running = False

    @property
    def stream_name(self) -> str:
        return self._manifest_path.stem

    async def start(self) -> None:
        raw: dict[str, Any] = json.loads(self._manifest_path.read_text())
        result = self._manifests.update_signal_manifest(raw)

        if result.warning:
            await self._bus.publish(
                Topics.WARNING,
                WarningEvent(source=self.stream_name, message=result.warning),
            )
        if not result.accepted:
            log.error("replay_source: manifest refused (%s)", result.warning)
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

    # ── private ───────────────────────────────────────────────────────────────

    async def _stream(self) -> None:
        manifest = self._manifests.signal_manifest
        assert manifest is not None

        channel_names = [ch["name"] for ch in manifest["channels"]]
        channel_types = {ch["name"]: ch["type"] for ch in manifest["channels"]}
        srate: float = manifest["stream"]["nominal_srate"]
        stream_name: str = manifest["stream"]["name"]
        interval = 1.0 / srate

        rows = list(csv.DictReader(self._csv_path.open()))
        source = itertools.cycle(rows) if self._loop else iter(rows)

        for row in source:
            if not self._running:
                break
            values: dict[str, float | str] = {}
            for name in channel_names:
                raw_val = row[name]
                values[name] = raw_val if channel_types[name] == "categorical" else float(raw_val)

            self._last_sample_at = time.monotonic()
            await self._bus.publish(
                Topics.SAMPLE,
                SampleEvent(stream_name=stream_name, timestamp=time.time(), values=values),
            )
            await asyncio.sleep(interval)

    async def _watchdog(self) -> None:
        """Emit a stale event if samples stop arriving within stale_timeout_s."""
        await asyncio.sleep(self._stale_timeout_s)
        while self._running:
            age = time.monotonic() - self._last_sample_at
            if self._last_sample_at > 0 and age > self._stale_timeout_s:
                manifest = self._manifests.signal_manifest
                name = manifest["stream"]["name"] if manifest else self.stream_name
                await self._bus.publish(
                    Topics.STALE,
                    StaleEvent(stream_name=name, age_s=age),
                )
            await asyncio.sleep(1.0)
