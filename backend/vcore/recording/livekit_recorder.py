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
        """Record the publisher's video track → <video_dir>/<session_id>.webm, anchored
        to LSL. Uses Track Egress (records one track directly — no headless-Chrome
        compositor, so it is reliable in Docker), recording the spectator camera the
        Unity publisher already streams for the live mirror."""
        if not self._cfg.enabled:
            return
        from livekit import api

        # Start-point sync anchor: capture LSL + wall clock at the moment egress starts.
        lsl_ts = _lsl_now()
        started_at = datetime.now(UTC).isoformat()

        # Egress writes inside its container at egress_out_dir, which is mounted to the
        # backend's video_dir on the host — so we store the backend-side path for serving.
        # Track egress of a VP8 video track produces a WebM.
        egress_path = f"{self._cfg.egress_out_dir.rstrip('/')}/{session_id}.webm"
        backend_path = str(self._video_dir / f"{session_id}.webm")

        lk = api.LiveKitAPI(self._cfg.api_url, self._cfg.api_key, self._cfg.api_secret)
        try:
            track_id = await self._find_video_track(lk)
            if track_id is None:
                self._store.set_video(session_id, None, started_at, lsl_ts)
                log.warning(
                    "livekit: no video track in room %r — recording skipped "
                    "(is the Unity publisher running?)", self._cfg.room,
                )
                return

            info = await lk.egress.start_track_egress(
                api.TrackEgressRequest(
                    room_name=self._cfg.room,
                    track_id=track_id,
                    file=api.DirectFileOutput(filepath=egress_path),
                )
            )
            self._egress_id = info.egress_id
        except Exception as exc:
            # Recording is best-effort: a missing/unhealthy Egress must NOT abort the
            # session — signals and the live mirror continue. Still store the LSL anchor.
            self._store.set_video(session_id, None, started_at, lsl_ts)
            log.warning(
                "livekit: track egress did not start (%s); session continues "
                "without recording", exc,
            )
            return
        finally:
            await lk.aclose()

        # Persist path + LSL anchor immediately (so review can align even before close).
        self._store.set_video(session_id, backend_path, started_at, lsl_ts)
        log.info(
            "livekit: track egress %s started for %s (track=%s, lsl_ts=%.3f → %s)",
            self._egress_id, session_id, track_id, lsl_ts, backend_path,
        )

    async def _find_video_track(self, lk: object) -> str | None:
        """Return the SID of the first published video track in the room, or None."""
        from livekit import api

        resp = await lk.room.list_participants(  # type: ignore[attr-defined]
            api.ListParticipantsRequest(room=self._cfg.room)
        )
        for participant in resp.participants:
            for track in participant.tracks:
                if track.type == api.TrackType.VIDEO:
                    return str(track.sid)
        return None

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
