"""Token endpoint for LiveKit clients (Unity publisher, browser subscribers)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from vcore.recording.livekit_recorder import mint_token

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


@router.get("/token")
async def token(request: Request, identity: str, role: str = "subscriber") -> dict[str, str]:
    """Return a LiveKit access token + client URL for the shared room.

    ``role=publisher`` (Unity) may publish; ``role=subscriber`` (browser) may only watch.
    """
    cfg = request.app.state.config.livekit
    if not cfg.enabled:
        raise HTTPException(409, "LiveKit is disabled (set livekit.enabled / LIVEKIT_ENABLED)")
    if role not in ("publisher", "subscriber"):
        raise HTTPException(400, "role must be 'publisher' or 'subscriber'")
    if not identity:
        raise HTTPException(400, "identity is required")
    return mint_token(cfg, identity, can_publish=(role == "publisher"))
