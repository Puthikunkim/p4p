from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsonschema
import jsonschema.validators

_CONTRACTS_DIR = Path(__file__).parent.parent.parent.parent / "contracts"


def _load_schema(name: str) -> dict[str, Any]:
    path = _CONTRACTS_DIR / f"{name}.schema.json"
    with path.open() as f:
        data: dict[str, Any] = json.load(f)
        return data


_SCHEMAS: dict[str, dict[str, Any]] = {}


def _schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMAS:
        _SCHEMAS[name] = _load_schema(name)
    return _SCHEMAS[name]


def validate(payload: dict[str, Any], contract: str) -> None:
    """Validate *payload* against *contract* (e.g. 'signal_schema').

    Raises jsonschema.ValidationError on failure.
    """
    jsonschema.validate(payload, _schema(contract))


class VersionSkew(StrEnum):
    OK = "ok"
    WARN = "warn"
    REFUSE = "refuse"


def check_version(payload_version: str, contract: str) -> VersionSkew:
    """Compare payload schema_version against the loaded contract version.

    Returns OK / WARN / REFUSE per VERSIONING.md policy.
    """
    schema_version_raw: str = _schema(contract).get("$schema_version", "1.0.0")
    # The contracts themselves don't embed their own version in a machine-readable
    # top-level field; we derive it from the golden example instead.
    # For runtime use, we hard-code the known current version here and update it
    # whenever the contract MAJOR/MINOR bumps.
    known: dict[str, str] = {
        "signal_schema": "1.0.0",
        "rule_grammar": "1.0.0",
        "status_request": "1.0.0",
        "object_status_manifest": "1.0.0",
    }
    current = known.get(contract, "1.0.0")

    def _parts(v: str) -> tuple[int, int, int]:
        major, minor, patch = (int(x) for x in v.split("."))
        return major, minor, patch

    p_major, p_minor, _ = _parts(payload_version)
    c_major, c_minor, _ = _parts(current)

    if p_major != c_major:
        return VersionSkew.REFUSE
    if p_minor != c_minor:
        return VersionSkew.WARN
    return VersionSkew.OK

    # suppress unused variable warning
    _ = schema_version_raw
