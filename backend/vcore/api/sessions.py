"""REST API for recording session lifecycle and history."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
    return {"session_id": sid}


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str, request: Request) -> dict[str, Any]:
    recorder: Any = request.app.state.recorder
    if recorder.active_session_id != session_id:
        raise HTTPException(404, "No active session with that ID")
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


@router.post("/api/sessions/{session_id}/video-start")
async def video_start(session_id: str, request: Request) -> dict[str, Any]:
    """Record the wall-clock and LSL timestamp at which video recording began."""
    recorder: Any = request.app.state.recorder
    if recorder.store.get_session(session_id) is None:
        raise HTTPException(404, "Session not found")
    started_at = datetime.now(UTC).isoformat()
    lsl_ts: float | None = recorder.last_lsl_ts
    recorder.store.set_video(session_id, None, started_at, lsl_ts)
    return {"video_started_at": started_at, "video_lsl_ts": lsl_ts}


@router.post("/api/sessions/{session_id}/video", status_code=201)
async def upload_video(session_id: str, request: Request) -> dict[str, str]:
    """Accept a raw video blob (video/webm or video/mp4) and store it on disk."""
    recorder: Any = request.app.state.recorder
    video_store: Any = request.app.state.video_store
    if recorder.store.get_session(session_id) is None:
        raise HTTPException(404, "Session not found")
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty video body")
    content_type = request.headers.get("content-type", "video/webm")
    path = video_store.save_video(session_id, body, content_type)
    recorder.store.set_video(session_id, str(path))
    return {"video_path": str(path)}
