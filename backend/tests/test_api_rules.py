"""Phase 6 tests — rules REST API (POST/PUT/DELETE/trigger)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vcore.app import create_app

VALID_RULE: dict[str, Any] = {
    "id": "test-dim",
    "schema_version": "1.0.0",
    "description": "test rule",
    "enabled": True,
    "when": {"all": [{"signal": "cognitive_load", "op": ">=", "threshold": 0.8}]},
    "then": {
        "set": {
            "target": {"tag": "ambient_light"},
            "status": "brightness",
            "value": 20,
        },
        "cooldown_s": 5,
    },
}

OBJECT_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0.0",
    "scene": "test",
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
def client(tmp_path: Path) -> TestClient:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    app = create_app(rules_dir=rules_dir, sink_port=0)
    return TestClient(app)


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_rules_empty(client: TestClient) -> None:
    resp = client.get("/api/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rules"] == []
    assert data["disabled"] == {}


# ── create ────────────────────────────────────────────────────────────────────

def test_post_valid_rule_creates_file(client: TestClient, tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    resp = client.post("/api/rules", json=VALID_RULE)
    assert resp.status_code == 201
    assert (rules_dir / "test-dim.yaml").exists()


def test_post_invalid_rule_returns_422(client: TestClient, tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    resp = client.post("/api/rules", json={"not": "a-rule"})
    assert resp.status_code == 422
    assert not list(rules_dir.glob("*.yaml"))


def test_post_duplicate_rule_returns_409(client: TestClient) -> None:
    client.post("/api/rules", json=VALID_RULE)
    resp = client.post("/api/rules", json=VALID_RULE)
    assert resp.status_code == 409


def test_post_rule_appears_in_list(client: TestClient) -> None:
    client.post("/api/rules", json=VALID_RULE)
    resp = client.get("/api/rules")
    ids = [r["id"] for r in resp.json()["rules"]]
    assert "test-dim" in ids


# ── update ────────────────────────────────────────────────────────────────────

def test_put_updates_rule(client: TestClient, tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    client.post("/api/rules", json=VALID_RULE)
    updated = {**VALID_RULE, "description": "updated"}
    resp = client.put("/api/rules/test-dim", json=updated)
    assert resp.status_code in (200, 201)
    import yaml
    content = yaml.safe_load((rules_dir / "test-dim.yaml").read_text())
    assert content["description"] == "updated"


def test_put_rejects_id_mismatch(client: TestClient) -> None:
    resp = client.put("/api/rules/other-id", json=VALID_RULE)
    assert resp.status_code == 400


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_rule_removes_file(client: TestClient, tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    client.post("/api/rules", json=VALID_RULE)
    assert (rules_dir / "test-dim.yaml").exists()
    resp = client.delete("/api/rules/test-dim")
    assert resp.status_code == 204
    assert not (rules_dir / "test-dim.yaml").exists()


def test_delete_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.delete("/api/rules/no-such-rule")
    assert resp.status_code == 404


def test_delete_rule_disappears_from_list(client: TestClient) -> None:
    client.post("/api/rules", json=VALID_RULE)
    client.delete("/api/rules/test-dim")
    resp = client.get("/api/rules")
    ids = [r["id"] for r in resp.json()["rules"]]
    assert "test-dim" not in ids


# ── trigger ───────────────────────────────────────────────────────────────────

def test_trigger_nonexistent_rule_returns_404(client: TestClient) -> None:
    resp = client.post("/api/rules/no-such/trigger")
    assert resp.status_code == 404


def test_trigger_without_manifest_returns_422(client: TestClient) -> None:
    client.post("/api/rules", json=VALID_RULE)
    # No object-status manifest loaded → validate_request returns reason
    resp = client.post("/api/rules/test-dim/trigger")
    assert resp.status_code == 422


def test_trigger_with_manifest_fires(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    app = create_app(rules_dir=rules_dir, sink_port=0)
    with TestClient(app) as c:
        # Load manifests directly onto app state, then post rule, then trigger
        app.state.manifests.update_object_status_manifest(OBJECT_MANIFEST)
        c.post("/api/rules", json=VALID_RULE)
        resp = c.post("/api/rules/test-dim/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fired"]["source"] == "manual"
        assert data["fired"]["source_rule"] == "test-dim"
