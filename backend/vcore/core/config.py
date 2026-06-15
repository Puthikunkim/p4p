from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class IngestionConfig(BaseModel):
    lsl_streams: list[str] = ["sensor.cognitive"]
    stale_timeout_s: float = 5.0
    replay_fixture: str | None = None


class OutboundConfig(BaseModel):
    transport: str = "ws"
    runtime_ws_path: str = "/ws/runtime"
    reconnect_backoff_s: float = 2.0


class BridgeConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    dashboard_ws_path: str = "/ws/dashboard"
    bearer_token: str | None = None


class RecordingConfig(BaseModel):
    data_dir: str = "../data"
    xdf_enabled: bool = True
    sqlite_enabled: bool = True
    sqlite_path: str = "../data/vcore.db"


class VideoConfig(BaseModel):
    enabled: bool = True
    signaling_ws_path: str = "/ws/signaling"
    fallback_transport: str = "none"


class RulesConfig(BaseModel):
    rules_dir: str = "./rules"


class VCoreConfig(BaseModel):
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    outbound: OutboundConfig = Field(default_factory=OutboundConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)


def load_config(path: Path | str) -> VCoreConfig:
    raw: dict[str, Any] = {}
    config_path = Path(path)
    if config_path.exists():
        with config_path.open() as f:
            raw = yaml.safe_load(f) or {}
    return VCoreConfig(**raw)
