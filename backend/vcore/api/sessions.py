"""REST API for recording session lifecycle and history."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from vcore.recording.xdf_reader import load_xdf_signals

router = APIRouter()


class StartSessionBody(BaseModel):
    participant: str
    notes: str = ""


@router.post("/api/sessions", status_code=201)
async def start_session(body: StartSessionBody, request: Request) -> dict[str, str]:
    recorder: Any = request.app.state.recorder
    if recorder.active_session_id:
        raise HTTPException(409, "A session is already active")
    sid: str = recorder.start_session(body.participant, body.notes)
    await request.app.state.livekit_recorder.start(sid)  # no-op unless livekit.enabled
    return {"session_id": sid}


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(
    session_id: str, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    recorder: Any = request.app.state.recorder
    if recorder.active_session_id != session_id:
        raise HTTPException(404, "No active session with that ID")
    # End the session immediately (close the XDF + mark it done in the DB) so the UI flips
    # to "stopped" right away. Stopping the LiveKit egress is a slow round-trip to the
    # egress server (it finalises the WebM), so defer it to a background task rather than
    # blocking the response on it. The egress keeps its own state, so it stops correctly
    # even after the session row is marked ended.
    xdf_path: str | None = await recorder.stop_session()
    background_tasks.add_task(request.app.state.livekit_recorder.stop, session_id)
    return {"session_id": session_id, "xdf_path": xdf_path}


@router.get("/api/sessions")
async def list_sessions(request: Request) -> list[dict[str, Any]]:
    recorder: Any = request.app.state.recorder
    return recorder.store.list_sessions()  # type: ignore[no-any-return]


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    recorder: Any = request.app.state.recorder
    session: dict[str, Any] | None = recorder.store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, str]:
    """Delete a recorded session: its DB row + events, plus a best-effort cleanup of the
    XDF and video files it referenced. The active (recording) session cannot be deleted."""
    recorder: Any = request.app.state.recorder
    if recorder.active_session_id == session_id:
        raise HTTPException(409, "Cannot delete a session while it is recording; stop it first")
    deleted: dict[str, Any] | None = recorder.store.delete_session(session_id)
    if deleted is None:
        raise HTTPException(404, "Session not found")
    # A missing or locked file must not fail the delete — the DB row is already gone.
    for key in ("xdf_path", "video_path"):
        path = deleted.get(key)
        if path:
            with suppress(OSError):
                Path(path).unlink(missing_ok=True)
    return {"deleted": session_id}


@router.get("/api/sessions/{session_id}/video")
async def get_video(session_id: str, request: Request) -> FileResponse:
    """Stream the recorded session video for playback in Data History."""
    recorder: Any = request.app.state.recorder
    session: dict[str, Any] | None = recorder.store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    video_path = session.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(404, "No video recorded for this session")
    media_type = "video/mp4" if str(video_path).endswith(".mp4") else "video/webm"
    return FileResponse(video_path, media_type=media_type)


@router.get("/api/sessions/{session_id}/signals")
async def get_signals(session_id: str, request: Request) -> dict[str, Any]:
    """Return the numeric signal series recorded in the session's XDF, for video-synced
    review (LSL-clock timestamps the frontend aligns to the video via ``video_lsl_ts``)."""
    recorder: Any = request.app.state.recorder
    session: dict[str, Any] | None = recorder.store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    xdf_path = session.get("xdf_path")
    if not xdf_path or not Path(xdf_path).exists():
        raise HTTPException(404, "No signals recorded for this session")
    # XDF parsing is blocking; keep it off the event loop.
    return await asyncio.to_thread(load_xdf_signals, xdf_path)
