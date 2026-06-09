"""V-CORE composition root — wires all components and exposes the FastAPI app."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from vcore.api.rules import router as rules_router
from vcore.api.sessions import router as sessions_router
from vcore.bridge.signaling import SignalingBroker
from vcore.bridge.ws import DashboardBridge
from vcore.core.eventbus import EventBus
from vcore.core.schema import ActiveManifests
from vcore.engine.evaluator import RuleEvaluator
from vcore.engine.registry import RuleRegistry
from vcore.outbound.ws_sink import WsSink
from vcore.recording.recorder import Recorder
from vcore.recording.video_store import VideoStore

log = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent.parent / "rules"
_DATA_DIR = Path(__file__).parent.parent / "data"
_SINK_HOST = "localhost"
_SINK_PORT = 9001


def create_app(
    *,
    rules_dir: Path = _RULES_DIR,
    data_dir: Path = _DATA_DIR,
    sink_host: str = _SINK_HOST,
    sink_port: int = _SINK_PORT,
) -> FastAPI:
    """Create and return the FastAPI application.

    Pass ``rules_dir`` / ``sink_host`` / ``sink_port`` to override defaults in tests.
    All wired components are stored on ``app.state`` for route-handler access.
    """
    bus = EventBus()
    manifests = ActiveManifests()
    registry = RuleRegistry(rules_dir)
    evaluator = RuleEvaluator(registry, bus, manifests)
    ws_sink = WsSink(sink_host, sink_port, bus=bus, manifests=manifests)
    bridge = DashboardBridge(bus, manifests, registry, evaluator, ws_sink)
    recorder = Recorder(bus, manifests, data_dir)
    signaling = SignalingBroker()
    video_store = VideoStore(data_dir)

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
        log.info("V-CORE started (rules_dir=%s)", rules_dir)
        yield
        # ── shutdown ─────────────────────────────────────────────────────────
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
