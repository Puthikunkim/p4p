"""V-CORE composition root — wires all components and exposes the FastAPI app."""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from vcore.api.rules import router as rules_router
from vcore.api.sessions import router as sessions_router
from vcore.bridge.signaling import SignalingBroker
from vcore.bridge.ws import DashboardBridge
from vcore.core.config import VCoreConfig, load_config
from vcore.core.eventbus import EventBus
from vcore.core.schema import ActiveManifests
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry
from vcore.ingestion.lsl_source import LSLSource
from vcore.outbound.ws_sink import WsSink
from vcore.recording.recorder import Recorder
from vcore.recording.video_store import VideoStore

log = logging.getLogger(__name__)

# Backend directory (this file is backend/vcore/app.py → parents[1] == backend/).
# Relative config paths are resolved against this so behaviour is cwd-independent.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _default_config_path() -> Path:
    """Config file location: ``$VCORE_CONFIG`` if set, else ``backend/config.yaml``."""
    env = os.environ.get("VCORE_CONFIG")
    return Path(env) if env else _BACKEND_DIR / "config.yaml"


def _resolve(path: str | Path) -> Path:
    """Resolve a (possibly relative) config path against the backend directory."""
    p = Path(path)
    return p if p.is_absolute() else (_BACKEND_DIR / p)


def create_app(
    *,
    config: VCoreConfig | None = None,
    config_path: Path | str | None = None,
    rules_dir: Path | None = None,
    data_dir: Path | None = None,
    sink_host: str | None = None,
    sink_port: int | None = None,
) -> FastAPI:
    """Create and return the FastAPI application.

    Configuration comes from ``config.yaml`` (or ``$VCORE_CONFIG``); a missing
    file falls back to the defaults in :mod:`vcore.core.config`. The keyword
    arguments are **explicit overrides** (used by tests) that win over config.
    All wired components are stored on ``app.state`` for route-handler access.
    """
    if config is None:
        config = load_config(config_path if config_path is not None else _default_config_path())

    # ── resolve paths (explicit override → config → default), backend-anchored ──
    rules_dir = Path(rules_dir) if rules_dir is not None else _resolve(config.rules.rules_dir)
    # Recording artifact locations (Option C — fully granular). An umbrella
    # `data_dir` override (used by tests) roots all three beneath it; otherwise
    # xdf_dir / video_dir / sqlite_path are each taken independently from config.
    if data_dir is not None:
        data_dir = Path(data_dir)
        xdf_dir = data_dir / "xdf"
        video_dir = data_dir / "video"
        sqlite_path = data_dir / "vcore.db"
    else:
        xdf_dir = _resolve(config.recording.xdf_dir)
        video_dir = _resolve(config.recording.video_dir)
        sqlite_path = _resolve(config.recording.sqlite_path)

    sink_host = sink_host if sink_host is not None else config.outbound.ws_host
    sink_port = sink_port if sink_port is not None else config.outbound.ws_port

    manifest_path = _resolve(config.ingestion.manifest_path)
    stream_name = config.ingestion.lsl_streams[0] if config.ingestion.lsl_streams else None

    bus = EventBus()
    manifests = ActiveManifests()
    registry = RuleRegistry(rules_dir)
    evaluator = RuleEvaluator(registry, bus, manifests)
    ws_sink = WsSink(sink_host, sink_port, bus=bus, manifests=manifests)
    bridge = DashboardBridge(bus, manifests, registry, evaluator, ws_sink)
    recorder = Recorder(
        bus, manifests,
        xdf_dir=xdf_dir,
        sqlite_path=sqlite_path,
        xdf_enabled=config.recording.xdf_enabled,
    )
    signaling = SignalingBroker()
    video_store = VideoStore(video_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # ── startup ──────────────────────────────────────────────────────────
        registry.load_all()
        await evaluator.start()
        loop = asyncio.get_event_loop()
        registry.start_watching(evaluator.on_registry_change, loop)
        await ws_sink.start()
        await bridge.start()
        await recorder.start()

        lsl_source: LSLSource | None = None
        if stream_name and manifest_path.exists():
            lsl_source = LSLSource(
                stream_name=stream_name,
                manifest_path=manifest_path,
                bus=bus,
                manifests=manifests,
                stale_timeout_s=config.ingestion.stale_timeout_s,
            )
            bridge.signal_source = lsl_source
            await lsl_source.start()
            log.info("V-CORE LSL source started (stream=%s)", stream_name)

        log.info("V-CORE started (rules_dir=%s)", rules_dir)
        yield
        # ── shutdown ─────────────────────────────────────────────────────────
        if lsl_source is not None:
            await lsl_source.stop()
        await recorder.stop()
        await bridge.stop()
        await ws_sink.stop()
        registry.stop_watching()
        await evaluator.stop()
        log.info("V-CORE stopped")

    app = FastAPI(title="V-CORE", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store references for route-handler dependency injection via request.app.state
    app.state.config = config
    app.state.bus = bus
    app.state.manifests = manifests
    app.state.registry = registry
    app.state.evaluator = evaluator
    app.state.ws_sink = ws_sink
    app.state.bridge = bridge
    app.state.recorder = recorder
    app.state.signaling = signaling
    app.state.video_store = video_store
    app.state.rules_dir = rules_dir

    # ── routes ────────────────────────────────────────────────────────────────

    app.include_router(rules_router)
    app.include_router(sessions_router)

    @app.websocket("/ws/dashboard")
    async def ws_dashboard(ws: WebSocket) -> None:
        await bridge.handle_dashboard(ws)

    @app.websocket("/ws/runtime")
    async def ws_runtime(ws: WebSocket) -> None:
        await bridge.handle_runtime(ws)

    @app.websocket("/ws/signaling")
    async def ws_signaling(ws: WebSocket) -> None:
        await signaling.handle_peer(ws)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Module-level singleton used by `uvicorn vcore.app:app`
app = create_app()


def main() -> None:
    """Run with config-driven bind address: ``python -m vcore.app``.

    (For dev with autoreload, use ``uvicorn vcore.app:app --reload`` instead.)
    """
    import uvicorn

    cfg: VCoreConfig = app.state.config
    uvicorn.run(app, host=cfg.bridge.host, port=cfg.bridge.port)


if __name__ == "__main__":
    main()
