"""Typed configuration loaded from ``config.yaml`` (see ``app.create_app``).

Relative paths are resolved by the composition root against the backend
directory (the folder containing ``config.yaml``), so behaviour is independent
of the current working directory.

Each field below is annotated **(wired)** if ``app.py`` actually consumes it, or
**(reference only)** if it documents intent but is not yet read by the running
app — kept honest so the config never over-promises.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class IngestionConfig(BaseModel):
    # LSL stream name(s) to resolve; the first is the primary stream. (wired)
    lsl_streams: list[str] = ["sensor.cognitive"]
    # Contract-1 signal manifest (sidecar JSON) describing the stream's channels. (wired)
    manifest_path: str = "../tools/fixtures/full_session.manifest.json"
    # Seconds without a sample before the signal is marked stale. (wired)
    stale_timeout_s: float = 5.0


class OutboundConfig(BaseModel):
    # Standalone WsSink server bind, used by mock_unity / direct websockets clients. (wired)
    ws_host: str = "localhost"
    ws_port: int = 9001


class BridgeConfig(BaseModel):
    # Bind interface/port — used when launched via ``python -m vcore.app``. (wired via runner)
    host: str = "0.0.0.0"
    port: int = 8000
    # Optional bearer token; auth is not implemented yet. (reference only)
    bearer_token: str | None = None


class RecordingConfig(BaseModel):
    # Write raw signal streams to XDF per session. (wired)
    xdf_enabled: bool = True
    # Directory for per-session XDF files: <xdf_dir>/<session_id>.xdf. (wired)
    xdf_dir: str = "data/xdf"
    # Directory for per-session video files: <video_dir>/<session_id>.<ext>. (wired)
    video_dir: str = "data/video"
    # SQLite database file for sessions + events; the filename is configurable. (wired)
    sqlite_path: str = "data/vcore.db"


class RulesConfig(BaseModel):
    # Directory watched for YAML/JSON rule files (hot-reloaded by watchdog). (wired)
    rules_dir: str = "rules"


class LiveKitConfig(BaseModel):
    # Server-side recording + SFU via LiveKit. Stays off until the LiveKit clients
    # (frontend subscriber + Unity publisher) are in place. (wired)
    enabled: bool = False
    # Client-facing URL handed out in access tokens (browser/Unity connect here). (wired)
    url: str = "ws://localhost:7880"
    # Backend → LiveKit server API URL (in Docker: http://livekit:7880). (wired)
    api_url: str = "http://localhost:7880"
    # API key/secret — dev defaults; override via env (LIVEKIT_API_KEY/SECRET). (wired)
    api_key: str = "devkey"
    api_secret: str = "devsecretdevsecretdevsecretdevsecret12"
    # Fixed room all participants share (always-on live mirror). (wired)
    room: str = "vcore"
    # Egress container's output dir; maps to recording.video_dir on the host. (wired)
    egress_out_dir: str = "/out"


class VCoreConfig(BaseModel):
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    outbound: OutboundConfig = Field(default_factory=OutboundConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    livekit: LiveKitConfig = Field(default_factory=LiveKitConfig)


def load_config(path: Path | str) -> VCoreConfig:
    """Load and validate config from *path*. A missing file yields all defaults,
    so the app runs unconfigured with the same behaviour the defaults encode."""
    raw: dict[str, Any] = {}
    config_path = Path(path)
    if config_path.exists():
        with config_path.open() as f:
            raw = yaml.safe_load(f) or {}
    cfg = VCoreConfig(**raw)
    _apply_livekit_env(cfg)
    return cfg


def _apply_livekit_env(cfg: VCoreConfig) -> None:
    """Override LiveKit endpoints/secrets from env (12-factor: keeps secrets out of git
    and lets docker-compose point the backend at the in-network LiveKit server)."""
    env = os.environ
    if v := env.get("LIVEKIT_URL"):
        cfg.livekit.url = v
    if v := env.get("LIVEKIT_API_URL"):
        cfg.livekit.api_url = v
    if v := env.get("LIVEKIT_API_KEY"):
        cfg.livekit.api_key = v
    if v := env.get("LIVEKIT_API_SECRET"):
        cfg.livekit.api_secret = v
    if v := env.get("LIVEKIT_ENABLED"):
        cfg.livekit.enabled = v.lower() in ("1", "true", "yes", "on")
