"""REST API for recording session lifecycle and history."""
from __future__ import annotations

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
