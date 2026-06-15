"""Phase 6 tests — DashboardBridge WebSocket endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vcore.app import create_app

SIGNAL_MANIFEST = {
    "schema_version": "1.0.0",
    "stream": {"name": "sensor.cognitive", "source_id": "test", "nominal_srate": 10},
    "channels": [
        {
            "name": "cognitive_load",
            "unit": "normalized",
            "type": "scalar",
            "range": {"min": 0, "max": 1},
            "display": {"hint": "stat_card", "label": "Cognitive Load"},
        }
    ],
}

OBJECT_MANIFEST = {
    "schema_version": "1.0.0",
    "scene": "test_scene",
    "runtime": "mock",
    "objects": [
        {
            "id": "light-1",
            "tags": ["ambient_light"],
            "statuses": [
                {"name": "brightness", "type": "continuous", "range": {"min": 0, "max": 100}}
            ],
        }
    ],
    "abstract_actions": [],
}


@pytest.fixture()
def app(tmp_path: Path):  # type: ignore[return]
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    return create_app(rules_dir=rules_dir, sink_port=0)


# ── on-connect state push ─────────────────────────────────────────────────────

def test_dashboard_receives_signal_manifest_on_connect(app) -> None:  # type: ignore[no-untyped-def]
    app.state.manifests.update_signal_manifest(SIGNAL_MANIFEST)
    with TestClient(app) as client, client.websocket_connect("/ws/dashboard") as ws:
        messages = _collect(ws, count=1, looking_for="signal_manifest")
    assert any(m["type"] == "signal_manifest" for m in messages)
    assert messages[0]["payload"]["stream"]["name"] == "sensor.cognitive"


def test_dashboard_receives_object_status_manifest_on_connect(app) -> None:  # type: ignore[no-untyped-def]
    app.state.manifests.update_signal_manifest(SIGNAL_MANIFEST)
    app.state.manifests.update_object_status_manifest(OBJECT_MANIFEST)
    with TestClient(app) as client, client.websocket_connect("/ws/dashboard") as ws:
        messages = _collect(ws, count=3, looking_for="object_status_manifest")
    types = {m["type"] for m in messages}
    assert "signal_manifest" in types
    assert "object_status_manifest" in types


def test_dashboard_receives_rule_list_on_connect(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as client, client.websocket_connect("/ws/dashboard") as ws:
        # rule_list arrives within the on-connect snapshot (after any manifests);
        # read enough of it to find rule_list (_collect breaks early on match).
        messages = _collect(ws, count=8, looking_for="rule_list")
    assert any(m["type"] == "rule_list" for m in messages)
    rl = next(m for m in messages if m["type"] == "rule_list")
    assert "rules" in rl["payload"]
    assert "disabled" in rl["payload"]


# ── healthz ───────────────────────────────────────────────────────────────────

def test_healthz(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect(ws, count: int, looking_for: str) -> list[dict]:  # type: ignore[no-untyped-def]
    """Read up to *count* messages or stop once *looking_for* type is seen."""
    messages = []
    for _ in range(count):
        try:
            raw = ws.receive_text()
            msg = json.loads(raw)
            messages.append(msg)
            if msg.get("type") == looking_for:
                break
        except Exception:
            break
    return messages
