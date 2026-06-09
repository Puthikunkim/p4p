"""Tests for the WebRTC SignalingBroker."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from vcore.bridge.signaling import SignalingBroker

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_app(broker: SignalingBroker) -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws/signaling")
    async def endpoint(ws: WebSocket) -> None:
        await broker.handle_peer(ws)

    return app


# ── registration ──────────────────────────────────────────────────────────────

def test_publisher_receives_registered() -> None:
    broker = SignalingBroker()
    with (TestClient(_make_app(broker)) as client,
          client.websocket_connect("/ws/signaling") as ws):
        ws.send_json({"role": "publisher"})
        msg = ws.receive_json()
    assert msg["type"] == "registered"
    assert msg["role"] == "publisher"
    assert "peer_id" in msg


def test_subscriber_receives_registered() -> None:
    broker = SignalingBroker()
    with (TestClient(_make_app(broker)) as client,
          client.websocket_connect("/ws/signaling") as ws):
        ws.send_json({"role": "subscriber"})
        msg = ws.receive_json()
    assert msg["type"] == "registered"
    assert msg["role"] == "subscriber"
    assert "peer_id" in msg


def test_subscriber_defaults_to_subscriber_role() -> None:
    broker = SignalingBroker()
    with (TestClient(_make_app(broker)) as client,
          client.websocket_connect("/ws/signaling") as ws):
        ws.send_json({})  # no role
        msg = ws.receive_json()
    assert msg["role"] == "subscriber"


# ── publisher-available notification ─────────────────────────────────────────

def test_subscriber_told_publisher_available_when_publisher_already_connected() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as pub:
        pub.send_json({"role": "publisher"})
        pub.receive_json()  # registered

        with client.websocket_connect("/ws/signaling") as sub:
            sub.send_json({"role": "subscriber"})
            sub.receive_json()  # registered
            avail = sub.receive_json()

    assert avail["type"] == "publisher-available"


def test_publisher_not_connected_subscriber_gets_no_publisher_available() -> None:
    broker = SignalingBroker()
    with (TestClient(_make_app(broker)) as client,
          client.websocket_connect("/ws/signaling") as sub):
        sub.send_json({"role": "subscriber"})
        reg = sub.receive_json()
    # Only one message: "registered", no publisher-available
    assert reg["type"] == "registered"
    assert not broker.publisher_connected


# ── message relay ─────────────────────────────────────────────────────────────

def test_offer_relayed_from_subscriber_to_publisher() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    relayed: dict[str, Any] = {}

    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as pub:
        pub.send_json({"role": "publisher"})
        pub.receive_json()

        with client.websocket_connect("/ws/signaling") as sub:
            sub.send_json({"role": "subscriber"})
            sub_reg = sub.receive_json()
            sub.receive_json()  # publisher-available
            sub_id = sub_reg["peer_id"]

            sub.send_json({"type": "offer", "sdp": "v=0..."})
            relayed = pub.receive_json()

    assert relayed["type"] == "offer"
    assert relayed["sdp"] == "v=0..."
    assert relayed["peer_id"] == sub_id


def test_answer_relayed_from_publisher_to_subscriber() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    relayed: dict[str, Any] = {}

    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as pub:
        pub.send_json({"role": "publisher"})
        pub.receive_json()

        with client.websocket_connect("/ws/signaling") as sub:
            sub.send_json({"role": "subscriber"})
            sub_reg = sub.receive_json()
            sub.receive_json()  # publisher-available
            sub_id = sub_reg["peer_id"]

            # Sub sends offer, pub receives it
            sub.send_json({"type": "offer", "sdp": "v=0..."})
            pub.receive_json()

            # Pub sends answer targeted at sub
            pub.send_json({"type": "answer", "sdp": "a=...", "peer_id": sub_id})
            relayed = sub.receive_json()

    assert relayed["type"] == "answer"
    assert relayed["sdp"] == "a=..."


def test_ice_candidate_relayed_subscriber_to_publisher() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    relayed: dict[str, Any] = {}

    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as pub:
        pub.send_json({"role": "publisher"})
        pub.receive_json()

        with client.websocket_connect("/ws/signaling") as sub:
            sub.send_json({"role": "subscriber"})
            sub.receive_json()
            sub.receive_json()  # publisher-available

            sub.send_json({"type": "ice-candidate", "candidate": {"sdpMid": "0"}})
            relayed = pub.receive_json()

    assert relayed["type"] == "ice-candidate"
    assert relayed["candidate"]["sdpMid"] == "0"


# ── publisher-gone ────────────────────────────────────────────────────────────

def test_subscriber_notified_when_publisher_disconnects() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    gone_msg: dict[str, Any] = {}

    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as sub:
        sub.send_json({"role": "subscriber"})
        sub.receive_json()  # registered (no publisher-available yet)

        with client.websocket_connect("/ws/signaling") as pub:
            pub.send_json({"role": "publisher"})
            pub.receive_json()
            avail = sub.receive_json()
            assert avail["type"] == "publisher-available"
        # pub disconnects here (context manager exit)

        gone_msg = sub.receive_json()

    assert gone_msg["type"] == "publisher-gone"


# ── broker state ──────────────────────────────────────────────────────────────

def test_publisher_connected_property() -> None:
    broker = SignalingBroker()
    assert not broker.publisher_connected
    app = _make_app(broker)
    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as pub:
        pub.send_json({"role": "publisher"})
        pub.receive_json()
        assert broker.publisher_connected
    assert not broker.publisher_connected


def test_subscriber_count() -> None:
    broker = SignalingBroker()
    app = _make_app(broker)
    with TestClient(app) as client, client.websocket_connect("/ws/signaling") as s1:
        s1.send_json({"role": "subscriber"})
        s1.receive_json()
        with client.websocket_connect("/ws/signaling") as s2:
            s2.send_json({"role": "subscriber"})
            s2.receive_json()
            assert broker.subscriber_count == 2
        assert broker.subscriber_count == 1
    assert broker.subscriber_count == 0


# ── video API (via full app) ──────────────────────────────────────────────────

@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    from vcore.app import create_app
    return TestClient(create_app(rules_dir=tmp_path / "rules", data_dir=tmp_path / "data", sink_port=0))


def test_video_start_session_not_found(app_client: TestClient) -> None:
    resp = app_client.post("/api/sessions/nope/video-start")
    assert resp.status_code == 404


def test_video_start_records_timestamp(app_client: TestClient) -> None:
    sid = app_client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    resp = app_client.post(f"/api/sessions/{sid}/video-start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_started_at"] is not None
    assert body["video_lsl_ts"] is None  # no LSL source active


def test_video_upload_stores_file(app_client: TestClient, tmp_path: Path) -> None:
    sid = app_client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    fake_video = b"RIFF\x00\x00\x00\x00WEBP"
    resp = app_client.post(
        f"/api/sessions/{sid}/video",
        content=fake_video,
        headers={"content-type": "video/webm"},
    )
    assert resp.status_code == 201
    assert resp.json()["video_path"].endswith(".webm")


def test_video_upload_empty_body_rejected(app_client: TestClient) -> None:
    sid = app_client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    resp = app_client.post(f"/api/sessions/{sid}/video", content=b"",
                           headers={"content-type": "video/webm"})
    assert resp.status_code == 400


def test_video_path_appears_in_session_detail(app_client: TestClient) -> None:
    sid = app_client.post("/api/sessions", json={"participant": "P01"}).json()["session_id"]
    fake_video = b"fake-video-content"
    app_client.post(f"/api/sessions/{sid}/video", content=fake_video,
                    headers={"content-type": "video/webm"})
    session = app_client.get(f"/api/sessions/{sid}").json()
    assert session["video_path"] is not None
