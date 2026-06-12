"""Contract tests — validate every golden example against its JSON Schema.

Valid goldens must pass; invalid goldens must raise ValidationError.
Both sides (jsonschema + pydantic models) are exercised.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from vcore.core import schema as vschema
from vcore.core.models import (
    ObjectStatusManifest,
    Rule,
    SignalManifest,
    StatusRequest,
)

EXAMPLES = Path(__file__).parent.parent.parent / "contracts" / "examples"

CONTRACT_MAP = {
    "signal_schema": SignalManifest,
    "rule_grammar": Rule,
    "status_request": StatusRequest,
    "object_status_manifest": ObjectStatusManifest,
}


def _load(name: str) -> dict:
    with (EXAMPLES / name).open() as f:
        data = json.load(f)
    # Strip the meta-key used for human documentation
    data.pop("_invalid_reason", None)
    return data


# ── jsonschema validation ─────────────────────────────────────────────────────

@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_valid_golden_passes_jsonschema(contract: str) -> None:
    payload = _load(f"{contract}.valid.json")
    vschema.validate(payload, contract)  # must not raise


@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_invalid_golden_fails_jsonschema(contract: str) -> None:
    payload = _load(f"{contract}.invalid.json")
    with pytest.raises(jsonschema.ValidationError):
        vschema.validate(payload, contract)


# ── pydantic round-trip ───────────────────────────────────────────────────────

@pytest.mark.parametrize("contract,model_cls", list(CONTRACT_MAP.items()))
def test_valid_golden_round_trips_pydantic(contract: str, model_cls: type) -> None:
    payload = _load(f"{contract}.valid.json")
    instance = model_cls.model_validate(payload)
    assert instance.schema_version == "1.0.0"


# ── Contract 4 (VR Context) — envelope without schema_version ─────────────────

def test_vr_context_valid_golden_passes_jsonschema() -> None:
    payload = _load("vr_context.valid.json")
    vschema.validate(payload, "vr_context")  # must not raise


def test_vr_context_invalid_golden_fails_jsonschema() -> None:
    payload = _load("vr_context.invalid.json")
    with pytest.raises(jsonschema.ValidationError):
        vschema.validate(payload, "vr_context")


# ── Contract 5 (Unity Behaviour) — manifest + sample envelopes ────────────────

def test_unity_behaviour_valid_golden_passes_jsonschema() -> None:
    payload = _load("unity_behaviour.valid.json")
    vschema.validate(payload, "unity_behaviour")  # must not raise


def test_unity_behaviour_invalid_golden_fails_jsonschema() -> None:
    payload = _load("unity_behaviour.invalid.json")
    with pytest.raises(jsonschema.ValidationError):
        vschema.validate(payload, "unity_behaviour")


# ── version-skew checks ───────────────────────────────────────────────────────

@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_same_version_is_ok(contract: str) -> None:
    assert vschema.check_version("1.0.0", contract) == vschema.VersionSkew.OK


@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_minor_bump_is_warn(contract: str) -> None:
    assert vschema.check_version("1.1.0", contract) == vschema.VersionSkew.WARN


@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_patch_bump_is_ok(contract: str) -> None:
    assert vschema.check_version("1.0.1", contract) == vschema.VersionSkew.OK


@pytest.mark.parametrize("contract", list(CONTRACT_MAP))
def test_major_bump_is_refuse(contract: str) -> None:
    assert vschema.check_version("2.0.0", contract) == vschema.VersionSkew.REFUSE
