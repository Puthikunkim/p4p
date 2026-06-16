"""Coordinates XDF writing and SQLite persistence for a recording session."""
from __future__ import annotations

import logging
from pathlib import Path

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    LinkStatusEvent,
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

    def __init__(
        self,
        bus: EventBus,
        manifests: ActiveManifests,
        *,
        xdf_dir: Path,
        sqlite_path: Path,
        xdf_enabled: bool = True,
    ) -> None:
        self._bus = bus
        self._manifests = manifests
        self._xdf_dir = Path(xdf_dir)
        self._xdf_enabled = xdf_enabled
        self._store = SqliteStore(Path(sqlite_path))
        self._session_id: str | None = None
        self._xdf: XdfWriter | None = None
        self._last_lsl_ts: float | None = None
        self._link_state: dict[str, str] = {}           # latest state per link (always tracked)
        self._recorded_link_state: dict[str, str] = {}   # last recorded state per link (dedupe)

    async def start(self) -> None:
        self._bus.subscribe(Topics.SAMPLE, self._on_sample)
        self._bus.subscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.subscribe(Topics.WARNING, self._on_warning)
        self._bus.subscribe(Topics.VR_CONTEXT, self._on_vr_context)
        self._bus.subscribe(Topics.LINK_STATUS, self._on_link_status)

    async def stop(self) -> None:
        self._bus.unsubscribe(Topics.SAMPLE, self._on_sample)
        self._bus.unsubscribe(Topics.RULE_FIRED, self._on_rule_fired)
        self._bus.unsubscribe(Topics.WARNING, self._on_warning)
        self._bus.unsubscribe(Topics.VR_CONTEXT, self._on_vr_context)
        self._bus.unsubscribe(Topics.LINK_STATUS, self._on_link_status)
        if self._session_id:
            await self.stop_session()
        self._store.close()

    def start_session(self, participant: str, notes: str = "") -> str:
        if self._session_id:
            raise RuntimeError("Session already active")
        self._session_id = self._store.create_session(participant, notes)
        # Snapshot the current connectivity as the session's baseline, then record
        # only subsequent changes (see _on_link_status).
        self._recorded_link_state = {}
        for link, state in self._link_state.items():
            self._store.record_event(self._session_id, "link_status", link, {"link": link, "state": state})
            self._recorded_link_state[link] = state
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

    async def _on_link_status(self, event: LinkStatusEvent) -> None:
        # Track the latest state for every link (so a new session can baseline it),
        # but record a session event only when a link's state actually changes —
        # so repeated 'down' retries while a stream is absent don't flood the log.
        self._link_state[event.link] = event.state
        if not self._session_id:
            return
        if self._recorded_link_state.get(event.link) == event.state:
            return
        self._recorded_link_state[event.link] = event.state
        self._store.record_event(
            self._session_id,
            "link_status",
            event.link,
            {"link": event.link, "state": event.state, "detail": event.detail},
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _open_xdf(self) -> None:
        if not self._xdf_enabled:
            return
        raw = self._manifests.signal_manifest
        if raw is None or not self._session_id:
            return
        manifest = SignalManifest.model_validate(raw)
        writer = XdfWriter(
            self._xdf_dir / f"{self._session_id}.xdf",
            manifest,
        )
        if not writer.has_numeric_channels:
            return
        writer.open()
        self._xdf = writer
        log.info("XDF recording started: %s", writer._path)
