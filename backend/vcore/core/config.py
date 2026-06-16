"""Typed configuration loaded from ``config.yaml`` (see ``app.create_app``).

Relative paths are resolved by the composition root against the backend
directory (the folder containing ``config.yaml``), so behaviour is independent
of the current working directory.

Each field below is annotated **(wired)** if ``app.py`` actually consumes it, or
**(reference only)** if it documents intent but is not yet read by the running
app — kept honest so the config never over-promises.
"""
from __future__ import annotations

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
    # Offline replay fixture — ReplaySource is test-only, not wired into app.py. (reference only)
    replay_fixture: str | None = None


class OutboundConfig(BaseModel):
    # Control transport. Only 'ws' is implemented; 'zmq' is a documented stub. (reference only)
    transport: str = "ws"
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


class VCoreConfig(BaseModel):
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    outbound: OutboundConfig = Field(default_factory=OutboundConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)


def load_config(path: Path | str) -> VCoreConfig:
    """Load and validate config from *path*. A missing file yields all defaults,
    so the app runs unconfigured with the same behaviour the defaults encode."""
    raw: dict[str, Any] = {}
    config_path = Path(path)
    if config_path.exists():
        with config_path.open() as f:
            raw = yaml.safe_load(f) or {}
    return VCoreConfig(**raw)
