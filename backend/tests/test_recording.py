"""Tests for XdfWriter, SqliteStore, Recorder, and the sessions API."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pyxdf
from fastapi.testclient import TestClient

from vcore.app import create_app
from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import (
    LinkStatusEvent,
    SampleEvent,
    SignalManifest,
    StatusRequest,
    VrContextEvent,
    WarningEvent,
)
from vcore.core.schema import ActiveManifests
from vcore.recording.recorder import Recorder
from vcore.recording.sqlite_store import SqliteStore
from vcore.recording.xdf_writer import XdfWriter

# ── shared fixtures ───────────────────────────────────────────────────────────

_MANIFEST_DICT: dict[str, Any] = {
    "schema_version": "1.0.0",
    "stream": {"name": "test_stream", "source_id": "src-01", "nominal_srate": 10.0},
    "channels": [
        {"name": "alpha", "unit": "uV^2", "type": "timeseries",
         "display": {"hint": "line_chart", "label": "Alpha"}},
        {"name": "load", "unit": "normalized", "type": "scalar",
         "display": {"hint": "stat_card", "label": "Load"}},
    ],
}


@pytest.fixture
def manifest() -> SignalManifest:
    return SignalManifest.model_validate(_MANIFEST_DICT)


# ── XdfWriter ─────────────────────────────────────────────────────────────────

def test_xdf_roundtrip(manifest: SignalManifest, tmp_path: Path) -> None:
    path = tmp_path / "out.xdf"
    w = XdfWriter(path, manifest)
    w.open()
    w.write_sample(SampleEvent(stream_name="s", timestamp=1.0, values={"alpha": 0.5, "load": 0.8}))
    w.write_sample(SampleEvent(stream_name="s", timestamp=2.0, values={"alpha": 0.6, "load": 0.7}))
    w.close()

    streams, _ = pyxdf.load_xdf(str(path))
    assert len(streams) == 1
    assert streams[0]["info"]["name"] == ["test_stream"]
    assert streams[0]["time_series"].shape == (2, 2)
    assert abs(streams[0]["time_stamps"][0] - 1.0) < 0.01


def test_xdf_skips_categorical(tmp_path: Path) -> None:
    manifest = SignalManifest.model_validate({
        **_MANIFEST_DICT,
        "channels": [
            *_MANIFEST_DICT["channels"],
            {"name": "mood", "unit": "category", "type": "categorical",
             "display": {"hint": "quadrant", "label": "Mood"}},
        ],
    })
    path = tmp_path / "out.xdf"
    w = XdfWriter(path, manifest)
    w.open()
    w.write_sample(SampleEvent(stream_name="s", timestamp=1.0,
                               values={"alpha": 0.5, "load": 0.8, "mood": "calm"}))
    w.close()

    streams, _ = pyxdf.load_xdf(str(path))
    assert streams[0]["time_series"].shape[1] == 2


def test_xdf_empty_session_readable(manifest: SignalManifest, tmp_path: Path) -> None:
    path = tmp_path / "empty.xdf"
    w = XdfWriter(path, manifest)
    w.open()
    w.close()
    streams, _ = pyxdf.load_xdf(str(path))
    assert len(streams) == 1


def test_xdf_no_numeric_channels(tmp_path: Path) -> None:
    manifest = SignalManifest.model_validate({
        **_MANIFEST_DICT,
        "channels": [
            {"name": "mood", "unit": "category", "type": "categorical",
             "display": {"hint": "quadrant", "label": "Mood"}},
        ],
    })
    w = XdfWriter(tmp_path / "out.xdf", manifest)
    assert not w.has_numeric_channels


# ── SqliteStore ───────────────────────────────────────────────────────────────

def test_sqlite_create_and_list(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.create_session("P01", "notes")
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["participant"] == "P01"
    assert sessions[0]["status"] == "running"
    store.close()


def test_sqlite_end_session(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    sid = store.create_session("P01")
    store.end_session(sid, "/data/signals.xdf")
    s = store.get_session(sid)
    assert s is not None
    assert s["status"] == "done"
    assert s["xdf_path"] == "/data/signals.xdf"
    assert s["ended_at"] is not None
    store.close()


def test_sqlite_record_events(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    sid = store.create_session("P01")
    store.record_event(sid, "rule_fired", "my-rule", {"intent_id": "abc"})
    store.record_event(sid, "warning", "engine", {"message": "stale"})
    s = store.get_session(sid)
    assert s is not None
    assert len(s["events"]) == 2
    assert s["events"][0]["event_type"] == "rule_fired"
    store.close()


def test_sqlite_event_count_in_list(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    sid = store.create_session("P01")
    store.record_event(sid, "rule_fired", "r", {})
    store.record_event(sid, "rule_fired", "r", {})
    assert store.list_sessions()[0]["event_count"] == 2
    store.close()


def test_sqlite_get_nonexistent(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    assert store.get_session("nope") is None
    store.close()


# ── Recorder ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def rec_fixture(
    tmp_path: Path, manifest: SignalManifest
) -> AsyncGenerator[tuple[EventBus, Recorder], None]:
    bus = EventBus()
    manifests = ActiveManifests()
    manifests.update_signal_manifest(manifest.model_dump(exclude_none=True))
    rec = Recorder(bus, manifests, tmp_path / "data")
    await rec.start()
    yield bus, rec
    if rec.active_session_id:
        await rec.stop_session()
    await rec.stop()


async def test_recorder_start_stop(rec_fixture: tuple[EventBus, Recorder]) -> None:
    _, rec = rec_fixture
    sid = rec.start_session("P01", "notes")
    assert rec.active_session_id == sid
    await rec.stop_session()
    assert rec.active_session_id is None
    sessions = rec.store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "done"


async def test_recorder_writes_xdf(
    rec_fixture: tuple[EventBus, Recorder], tmp_path: Path
) -> None:
    bus, rec = rec_fixture
    sid = rec.start_session("P01")
    await bus.publish(Topics.SAMPLE, SampleEvent(stream_name="s", timestamp=1.0,
                                                  values={"alpha": 0.5, "load": 0.8}))
    await bus.publish(Topics.SAMPLE, SampleEvent(stream_name="s", timestamp=2.0,
                                                  values={"alpha": 0.6, "load": 0.9}))
    await rec.stop_session()
    s = rec.store.get_session(sid)
    assert s is not None and s["xdf_path"] is not None
    streams, _ = pyxdf.load_xdf(s["xdf_path"])
    assert streams[0]["time_series"].shape[0] == 2


async def test_recorder_records_rule_fired(rec_fixture: tuple[EventBus, Recorder]) -> None:
    bus, rec = rec_fixture
    sid = rec.start_session("P01")
    req = StatusRequest(
        schema_version="1.0.0", intent_id="abc",
        timestamp="2024-01-01T00:00:00Z",
        target={"tag": "light"}, status="brightness", value=20,
        source_rule="my-rule", source="engine",
    )
    await bus.publish(Topics.RULE_FIRED, req)
    await rec.stop_session()
    s = rec.store.get_session(sid)
    assert s is not None
    assert s["events"][0]["event_type"] == "rule_fired"


async def test_recorder_records_warning(rec_fixture: tuple[EventBus, Recorder]) -> None:
    bus, rec = rec_fixture
    sid = rec.start_session("P01")
    await bus.publish(Topics.WARNING, WarningEvent(source="engine", message="stale signal"))
    await rec.stop_session()
    s = rec.store.get_session(sid)
    assert s is not None
    assert s["events"][0]["event_type"] == "warning"


async def test_recorder_records_vr_context(rec_fixture: tuple[EventBus, Recorder]) -> None:
    bus, rec = rec_fixture
    sid = rec.start_session("P01")
    await bus.publish(Topics.VR_CONTEXT, VrContextEvent(
        fields={"scene": "Aisle 2", "step": "3 / 8", "items_left": 4},
    ))
    await rec.stop_session()
    s = rec.store.get_session(sid)
    assert s is not None
    ev = s["events"][0]
    assert ev["event_type"] == "vr_context"
    assert ev["source"] == "Aisle 2"  # scene used as the event source label
    import json as _json
    assert _json.loads(ev["payload"])["fields"]["step"] == "3 / 8"


async def test_recorder_records_link_status_baseline_and_changes(
    rec_fixture: tuple[EventBus, Recorder],
) -> None:
    bus, rec = rec_fixture
    # Observed before the session → becomes the baseline snapshot at session start.
    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="up"))
    sid = rec.start_session("P01")
    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="up"))    # dup → skipped
    await asyncio.sleep(0.01)
    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="down"))  # change → recorded
    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="down"))  # dup → skipped
    await asyncio.sleep(0.01)
    await bus.publish(Topics.LINK_STATUS, LinkStatusEvent(link="sensor-pipeline", state="up"))    # change → recorded
    await rec.stop_session()

    s = rec.store.get_session(sid)
    assert s is not None
    states = [json.loads(e["payload"])["state"] for e in s["events"] if e["event_type"] == "link_status"]
    assert states == ["up", "down", "up"]  # baseline, then deduped transitions


async def test_recorder_ignores_events_outside_session(
    rec_fixture: tuple[EventBus, Recorder],
) -> None:
    bus, rec = rec_fixture
    await bus.publish(Topics.SAMPLE, SampleEvent(stream_name="s", timestamp=1.0,
                                                  values={"alpha": 0.5}))
    assert rec.store.list_sessions() == []


async def test_recorder_double_start_raises(rec_fixture: tuple[EventBus, Recorder]) -> None:
    _, rec = rec_fixture
    rec.start_session("P01")
    with pytest.raises(RuntimeError, match="already active"):
        rec.start_session("P02")


# ── Sessions API ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        rules_dir=tmp_path / "rules",
        data_dir=tmp_path / "data",
        sink_port=0,
    )
    return TestClient(app)


def test_api_start_session(client: TestClient) -> None:
    resp = client.post("/api/sessions", json={"participant": "P01"})
    assert resp.status_code == 201
    assert "session_id" in resp.json()


def test_api_start_session_conflict(client: TestClient) -> None:
    client.post("/api/sessions", json={"participant": "P01"})
    resp = client.post("/api/sessions", json={"participant": "P02"})
    assert resp.status_code == 409


def test_api_stop_session(client: TestClient) -> None:
    sid = client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    resp = client.post(f"/api/sessions/{sid}/stop")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid


def test_api_stop_wrong_id(client: TestClient) -> None:
    client.post("/api/sessions", json={"participant": "P01"})
    assert client.post("/api/sessions/wrong/stop").status_code == 404


def test_api_list_sessions(client: TestClient) -> None:
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_list_shows_created_session(client: TestClient) -> None:
    client.post("/api/sessions", json={"participant": "P01", "notes": "hi"})
    sessions = client.get("/api/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["participant"] == "P01"


def test_api_get_session_not_found(client: TestClient) -> None:
    assert client.get("/api/sessions/nope").status_code == 404


def test_api_get_session_detail(client: TestClient) -> None:
    sid = client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    s = client.get(f"/api/sessions/{sid}").json()
    assert s["id"] == sid
    assert s["events"] == []


def test_api_video_upload_then_playback(client: TestClient) -> None:
    sid = client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    up = client.post(
        f"/api/sessions/{sid}/video",
        content=b"FAKEWEBMDATA",
        headers={"content-type": "video/webm"},
    )
    assert up.status_code == 201

    resp = client.get(f"/api/sessions/{sid}/video")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/webm")
    assert resp.content == b"FAKEWEBMDATA"


def test_api_get_video_missing(client: TestClient) -> None:
    sid = client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}/video").status_code == 404


def test_api_get_video_unknown_session(client: TestClient) -> None:
    assert client.get("/api/sessions/nope/video").status_code == 404
