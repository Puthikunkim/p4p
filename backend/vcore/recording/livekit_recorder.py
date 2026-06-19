"""Server-side session recording + token minting via LiveKit (media plane).

V-CORE stays the orchestrator: it mints access tokens for the Unity publisher and
browser subscribers, and starts/stops a LiveKit Egress recording of the shared
room per session. The recording is anchored to the LSL clock captured at egress
start, so the MP4 lines up with the XDF signal timeline (start-point alignment:
video t=0 ↔ the stored ``video_lsl_ts``).
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from vcore.core.config import LiveKitConfig
from vcore.recording.sqlite_store import SqliteStore

log = logging.getLogger(__name__)


def _lsl_now() -> float:
    """LSL clock so the recording shares the sensor pipeline's time domain."""
    try:
        import pylsl

        return float(pylsl.local_clock())
    except Exception:
        return time.time()


def mint_token(cfg: LiveKitConfig, identity: str, *, can_publish: bool) -> dict[str, str]:
    """Mint a LiveKit access token (+ client URL + room) for the shared room."""
    from livekit import api

    token = (
        api.AccessToken(cfg.api_key, cfg.api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=cfg.room,
                can_publish=can_publish,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )
    return {"token": token, "url": cfg.url, "room": cfg.room}


class LiveKitRecorder:
    """Drives LiveKit Egress to record the shared room for the active session."""

    def __init__(self, cfg: LiveKitConfig, store: SqliteStore, video_dir: Path) -> None:
        self._cfg = cfg
        self._store = store
        self._video_dir = Path(video_dir)
        self._egress_id: str | None = None

    @property
    def enabled(self) -> bool:
        return self._cfg.enabled

    async def start(self, session_id: str) -> None:
        """Start recording the room → <video_dir>/<session_id>.mp4, anchored to LSL."""
        if not self._cfg.enabled:
            return
        from livekit import api

        # Start-point sync anchor: capture LSL + wall clock at the moment egress starts.
        lsl_ts = _lsl_now()
        started_at = datetime.now(UTC).isoformat()

        # Egress writes inside its container at egress_out_dir, which is mounted to the
        # backend's video_dir on the host — so we store the backend-side path for serving.
        egress_path = f"{self._cfg.egress_out_dir.rstrip('/')}/{session_id}.mp4"
        backend_path = str(self._video_dir / f"{session_id}.mp4")

        lk = api.LiveKitAPI(self._cfg.api_url, self._cfg.api_key, self._cfg.api_secret)
        try:
            info = await lk.egress.start_room_composite_egress(
                api.RoomCompositeEgressRequest(
                    room_name=self._cfg.room,
                    layout="grid",
                    file_outputs=[
                        api.EncodedFileOutput(
                            file_type=api.EncodedFileType.MP4,
                            filepath=egress_path,
                        )
                    ],
                )
            )
            self._egress_id = info.egress_id
        finally:
            await lk.aclose()

        # Persist path + LSL anchor immediately (so review can align even before close).
        self._store.set_video(session_id, backend_path, started_at, lsl_ts)
        log.info(
            "livekit: egress %s started for %s (lsl_ts=%.3f → %s)",
            self._egress_id, session_id, lsl_ts, backend_path,
        )

    async def stop(self) -> None:
        """Stop the active egress, if any."""
        if not self._cfg.enabled or self._egress_id is None:
            return
        from livekit import api

        lk = api.LiveKitAPI(self._cfg.api_url, self._cfg.api_key, self._cfg.api_secret)
        try:
            await lk.egress.stop_egress(api.StopEgressRequest(egress_id=self._egress_id))
        except Exception as exc:  # stopping is best-effort; the file is already on disk
            log.warning("livekit: stop_egress failed: %s", exc)
        finally:
            await lk.aclose()
        log.info("livekit: egress %s stopped", self._egress_id)
        self._egress_id = None
