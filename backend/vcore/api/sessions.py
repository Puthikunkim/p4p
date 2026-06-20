"""REST API for recording session lifecycle and history."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
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
async def stop_session(session_id: str, request: Request) -> dict[str, Any]:
    recorder: Any = request.app.state.recorder
    if recorder.active_session_id != session_id:
        raise HTTPException(404, "No active session with that ID")
    await request.app.state.livekit_recorder.stop(session_id)  # no-op unless livekit.enabled
    xdf_path: str | None = await recorder.stop_session()
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
