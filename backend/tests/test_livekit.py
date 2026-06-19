"""Tests for the LiveKit token path (no LiveKit server required)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vcore.app import create_app
from vcore.core.config import LiveKitConfig
from vcore.recording.livekit_recorder import mint_token


def test_mint_token_returns_jwt_and_client_url() -> None:
    cfg = LiveKitConfig(
        enabled=True,
        api_key="devkey",
        api_secret="devsecretdevsecretdevsecretdevsecret12",
        room="vcore",
        url="ws://localhost:7880",
    )
    out = mint_token(cfg, "tester", can_publish=True)
    assert out["room"] == "vcore"
    assert out["url"] == "ws://localhost:7880"
    # A JWT is header.payload.signature → exactly two dots.
    assert out["token"].count(".") == 2


def test_token_endpoint_returns_409_when_disabled(tmp_path: Path) -> None:
    # Default config has livekit.enabled = False, so the endpoint must refuse.
    app = create_app(rules_dir=tmp_path / "rules", data_dir=tmp_path / "data", sink_port=0)
    client = TestClient(app)
    resp = client.get("/api/livekit/token", params={"identity": "x"})
    assert resp.status_code == 409
