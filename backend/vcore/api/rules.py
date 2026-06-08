from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vcore.core import schema as vschema
from vcore.core.eventbus import Topics
from vcore.core.models import StatusRequest
from vcore.outbound.ws_sink import _validate_request

router = APIRouter(prefix="/api/rules", tags=["rules"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _rules_dir(request: Request) -> Path:
    return Path(request.app.state.rules_dir)


def _registry(request: Request) -> Any:
    return request.app.state.registry


def _evaluator(request: Request) -> Any:
    return request.app.state.evaluator


def _bus(request: Request) -> Any:
    return request.app.state.bus


def _manifests(request: Request) -> Any:
    return request.app.state.manifests


# ── response models ───────────────────────────────────────────────────────────

class RuleError(BaseModel):
    path: str
    reason: str


class RuleListResponse(BaseModel):
    rules: list[dict[str, Any]]
    disabled: dict[str, str]
    errors: list[RuleError]


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=RuleListResponse)
async def list_rules(request: Request) -> RuleListResponse:
    reg = _registry(request)
    ev = _evaluator(request)
    return RuleListResponse(
        rules=[r.model_dump(mode="json") for r in reg.rules.values()],
        disabled=ev.disabled_rules,
        errors=[RuleError(path=e.path, reason=e.reason) for e in reg.errors],
    )


@router.post("", status_code=201)
async def create_rule(request: Request, body: dict[str, Any]) -> JSONResponse:
    return await _write_rule(request, body, mode="create")


@router.put("/{rule_id}")
async def update_rule(request: Request, rule_id: str, body: dict[str, Any]) -> JSONResponse:
    if body.get("id") and body["id"] != rule_id:
        raise HTTPException(400, "rule id in body does not match URL")
    body["id"] = rule_id
    return await _write_rule(request, body, mode="update")


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(request: Request, rule_id: str) -> None:
    _rules_dir(request)
    # Find any file whose loaded rule has this id
    reg = _registry(request)
    rules = reg.rules
    if rule_id not in rules:
        raise HTTPException(404, f"rule '{rule_id}' not found")
    # Find the file path from the registry internals
    target: Path | None = None
    for path, rid in reg._path_to_id.items():
        if rid == rule_id:
            target = path
            break
    if target is None or not target.exists():
        raise HTTPException(404, f"file for rule '{rule_id}' not found")
    target.unlink()
    reg._remove_file(target)
    await _bus(request).publish(Topics.RULES_UPDATED, None)


@router.post("/{rule_id}/trigger")
async def trigger_rule(request: Request, rule_id: str) -> JSONResponse:
    """Manually fire a rule's StatusRequest with source=manual."""
    reg = _registry(request)
    rules = reg.rules
    if rule_id not in rules:
        raise HTTPException(404, f"rule '{rule_id}' not found")
    rule = rules[rule_id]
    manifests = _manifests(request)
    reason = _validate_request(manifests.object_status_manifest, _make_req(rule, source="manual"))
    if reason:
        raise HTTPException(422, f"cannot fire: {reason}")
    req = _make_req(rule, source="manual")
    await _bus(request).publish(Topics.RULE_FIRED, req)
    return JSONResponse({"fired": req.model_dump(mode="json")})


# ── internals ─────────────────────────────────────────────────────────────────

async def _write_rule(request: Request, body: dict[str, Any], *, mode: str) -> JSONResponse:
    try:
        vschema.validate(body, "rule_grammar")
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    rule_id: str = body["id"]
    rules_dir = _rules_dir(request)
    rules_dir.mkdir(parents=True, exist_ok=True)
    dest = rules_dir / f"{rule_id}.yaml"

    if mode == "create" and dest.exists():
        raise HTTPException(409, f"rule '{rule_id}' already exists; use PUT to update")

    dest.write_text(yaml.dump(body, default_flow_style=False))
    reg = _registry(request)
    reg.load_all()
    await _bus(request).publish(Topics.RULES_UPDATED, None)
    return JSONResponse({"written": str(dest), "id": rule_id}, status_code=201 if mode == "create" else 200)


def _make_req(rule: Any, *, source: str) -> StatusRequest:
    return StatusRequest(
        schema_version="1.0.0",
        intent_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        target=rule.then.set.target,
        status=rule.then.set.status,
        value=rule.then.set.value,
        source_rule=rule.id,
        source=source,  # type: ignore[arg-type]  # "engine"|"manual" enforced by caller
    )
