"""Coordinates XDF writing and SQLite persistence for a recording session."""
from __future__ import annotations

import logging
from pathlib import Path

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    SampleEvent,
    SignalManifest,
    StatusRequest,
    VrContextEvent,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests
from vcore.recording.sqlite_store import SqliteStore
from vcore.recording.xdf_writer import XdfWriter

log = logging.getLogger(__name__)


class Recorder:
    """Subscribes to bus events and persists them to XDF + SQLite during a session."""

    def __init__(self, bus: EventBus, manifests: ActiveManifests, data_dir: Path) -> None:
        self._bus = bus
        self._manifests = manifests
        self._data_dir = data_dir
        self._store = SqliteStore(data_dir / "sessions.db")
        self._session_id: str | None = None
        self._xdf: XdfWriter | None = None
        self._last_lsl_ts: float | None = None

    async def start(self) -> None:
        self._bus.subscribe(Topics.SAMPLE, self._on_sample)
        self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.subscribe(Topics.WARNING, self._on_warning)
        self._bus.subscribe(Topics.VR_CONTEXT, self._on_vr_context)

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.SAMPLE, self._on_sample)
        self._bus.unsubscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.unsubscribe(Topics.WARNING, self._on_warning)
        self._bus.unsubscribe(Topics.VR_CONTEXT, self._on_vr_context)
        if self._session_id:
            await self.stop_session()
        self._store.close()

    def start_session(self, participant: str, notes: str = "") -> str:
        if self._session_id:
            raise RuntimeError("Session already active")
        self._session_id = self._store.create_session(participant, notes)
        manifest = self._manifests.signal_manifest
        if manifest:
            self._open_xdf()
        return self._session_id

    async def stop_session(self) -> str | None:
        if not self._session_id:
            raise RuntimeError("No active session")
        sid = self._session_id
        xdf_path: str | None = None
        if self._xdf:
            self._xdf.close()
            xdf_path = str(self._xdf._path)
            self._xdf = None
        self._store.end_session(sid, xdf_path)
        self._session_id = None
        log.info("session %s ended (xdf=%s)", sid, xdf_path)
        return xdf_path

    @property
    def active_session_id(self) -> str | None:
        return self._session_id

    @property
    def store(self) -> SqliteStore:
        return self._store

    # ── bus handlers ──────────────────────────────────────────────────────────

    @property
    def last_lsl_ts(self) -> float | None:
        return self._last_lsl_ts

    async def _on_sample(self, event: SampleEvent) -> None:
        self._last_lsl_ts = event.timestamp
        if not self._session_id:
            return
        if self._xdf is None:
            self._open_xdf()
        if self._xdf:
            self._xdf.write_sample(event)

    async def _on_rule_fired(self, event: StatusRequest) -> None:
        if not self._session_id:
            return
        self._store.record_event(
            self._session_id,
            "rule_fired",
            event.source_rule or event.source,
            event.model_dump(),
        )

    async def _on_warning(self, event: WarningEvent) -> None:
        if not self._session_id:
            return
        self._store.record_event(
            self._session_id,
            "warning",
            event.source,
            {"message": event.message},
        )

    async def _on_vr_context(self, event: VrContextEvent) -> None:
        if not self._session_id:
            return
        scene = event.fields.get("scene", "unity")
        self._store.record_event(
            self._session_id,
            "vr_context",
            str(scene),
            event.model_dump(mode="json"),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _open_xdf(self) -> None:
        raw = self._manifests.signal_manifest
        if raw is None or not self._session_id:
            return
        manifest = SignalManifest.model_validate(raw)
        writer = XdfWriter(
            self._data_dir / self._session_id / "signals.xdf",
            manifest,
        )
        if not writer.has_numeric_channels:
            return
        writer.open()
        self._xdf = writer
        log.info("XDF recording started: %s", writer._path)
