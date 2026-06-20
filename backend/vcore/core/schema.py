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
    _schema(contract).get("$schema_version", "1.0.0")
    # The contracts themselves don't embed their own version in a machine-readable
    # top-level field; we derive it from the golden example instead.
    # For runtime use, we hard-code the known current version here and update it
    # whenever the contract MAJOR/MINOR bumps.
    known: dict[str, str] = {
        "signal_schema": "1.0.0",
        "rule_grammar": "1.0.0",
        "status_request": "1.0.0",
        "action_request": "1.0.0",
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


class AcceptResult:
    """Returned by ActiveManifests.update_* methods."""

    def __init__(self, skew: VersionSkew, warning: str | None = None) -> None:
        self.skew = skew
        self.warning = warning

    @property
    def accepted(self) -> bool:
        return self.skew != VersionSkew.REFUSE


class ActiveManifests:
    """Holds the currently active Signal Schema and Object-Status Manifest.

    Each update validates the payload against its contract schema and checks
    version skew. Callers inspect AcceptResult.accepted before using the
    updated manifest; on REFUSE the previous manifest is kept unchanged.
    """

    def __init__(self) -> None:
        self._signal: dict[str, Any] | None = None
        self._behaviour_channels: list[dict[str, Any]] = []
        self._object_status: dict[str, Any] | None = None
        self._catalog: dict[str, Any] | None = None

    # ── Signal Schema (Contract 1) ────────────────────────────────────────

    def update_signal_manifest(self, payload: dict[str, Any]) -> AcceptResult:
        validate(payload, "signal_schema")
        skew = check_version(payload["schema_version"], "signal_schema")
        if skew == VersionSkew.REFUSE:
            return AcceptResult(skew, f"signal_schema major version mismatch: {payload['schema_version']}")
        self._signal = payload
        warning = f"signal_schema minor version skew: {payload['schema_version']}" if skew == VersionSkew.WARN else None
        return AcceptResult(skew, warning)

    def update_behaviour_channels(self, channels: list[dict[str, Any]]) -> None:
        """Merge Unity-declared behavioural channels (Contract 1 channel shape).

        These augment the active signal manifest so the dashboard renders them,
        the rule engine can reference them, and degradation keeps the matching
        rules enabled. Raises on a malformed channel. Channel names already
        present in the base (sensor-pipeline) manifest are ignored to avoid duplicates.
        """
        from vcore.core.models import Channel  # local import avoids import cycle
        for ch in channels:
            Channel.model_validate(ch)  # structural validation; raises on bad shape
        self._behaviour_channels = channels

    @property
    def signal_manifest(self) -> dict[str, Any] | None:
        """Active signal manifest = base (sensor-pipeline) manifest ⊕ Unity behavioural channels."""
        if self._signal is None:
            return None
        if not self._behaviour_channels:
            return self._signal
        base_names = {ch["name"] for ch in self._signal.get("channels", [])}
        extra = [ch for ch in self._behaviour_channels if ch["name"] not in base_names]
        if not extra:
            return self._signal
        merged = dict(self._signal)
        merged["channels"] = [*self._signal.get("channels", []), *extra]
        return merged

    # ── Object-Status Manifest (Contract 3b) ─────────────────────────────

    def update_object_status_manifest(self, payload: dict[str, Any]) -> AcceptResult:
        validate(payload, "object_status_manifest")
        skew = check_version(payload["schema_version"], "object_status_manifest")
        if skew == VersionSkew.REFUSE:
            return AcceptResult(skew, f"object_status_manifest major version mismatch: {payload['schema_version']}")
        self._object_status = payload
        warning = f"object_status_manifest minor version skew: {payload['schema_version']}" if skew == VersionSkew.WARN else None
        return AcceptResult(skew, warning)

    @property
    def object_status_manifest(self) -> dict[str, Any] | None:
        return self._object_status

    # ── Object-Status Catalog (project-wide; same shape as the manifest) ──
    # The manifest is what is loaded *now* (drives dispatch + degradation); the catalog
    # is the full set of objects/actions the project can ever expose (for authoring rules
    # ahead of time). Baked by the Unity editor and sent on connect.

    def update_catalog(self, payload: dict[str, Any]) -> AcceptResult:
        validate(payload, "object_status_manifest")
        skew = check_version(payload["schema_version"], "object_status_manifest")
        if skew == VersionSkew.REFUSE:
            return AcceptResult(skew, f"object_status_catalog major version mismatch: {payload['schema_version']}")
        self._catalog = payload
        warning = f"object_status_catalog minor version skew: {payload['schema_version']}" if skew == VersionSkew.WARN else None
        return AcceptResult(skew, warning)

    @property
    def object_status_catalog(self) -> dict[str, Any] | None:
        return self._catalog


# Module-level singleton — import and use directly.
manifests = ActiveManifests()
