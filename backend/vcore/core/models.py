from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ── Contract 1 — Signal Schema ────────────────────────────────────────────────

class DisplayHint(BaseModel):
    model_config = {"extra": "allow"}
    hint: str
    label: str
    precision: int | None = None
    window_s: float | None = None


class Channel(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    unit: str
    type: Literal["scalar", "timeseries", "categorical"]
    range: dict[str, float] | None = None
    categories: list[str] | None = None
    display: DisplayHint


class StreamMeta(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    source_id: str
    nominal_srate: float


class SignalManifest(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: str
    stream: StreamMeta
    channels: list[Channel]


# ── Contract 2 — Rule Grammar ─────────────────────────────────────────────────

class ConditionItem(BaseModel):
    model_config = {"extra": "forbid"}
    signal: str
    op: Literal[">", ">=", "<", "<=", "==", "!=", "between"]
    threshold: float | None = None
    low: float | None = None
    high: float | None = None
    value: str | None = None
    sustain_s: float | None = None


class ConditionGroup(BaseModel):
    model_config = {"extra": "forbid"}
    all: list[ConditionItem] | None = None
    any: list[ConditionItem] | None = None


class TagTarget(BaseModel):
    model_config = {"extra": "forbid"}
    tag: str


class IdTarget(BaseModel):
    model_config = {"extra": "forbid"}
    id: str


Target = TagTarget | IdTarget


class SetAction(BaseModel):
    model_config = {"extra": "forbid"}
    target: Target = Field(discriminator=None)
    status: str
    value: float | str


class InvokeAction(BaseModel):
    """Invoke a parameterless Unity action. No target = scene-level."""
    model_config = {"extra": "forbid"}
    action: str
    target: Target | None = None


class ThenClause(BaseModel):
    model_config = {"extra": "forbid"}
    set: SetAction | None = None
    action: InvokeAction | None = None
    cooldown_s: float | None = None

    @model_validator(mode="after")
    def _exactly_one_output(self) -> ThenClause:
        if (self.set is None) == (self.action is None):
            raise ValueError("rule 'then' must have exactly one of 'set' or 'action'")
        return self


class Rule(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    schema_version: str
    description: str | None = None
    enabled: bool = True
    when: ConditionGroup
    then: ThenClause


# ── Contract 3a — Status Request ──────────────────────────────────────────────

class StatusRequest(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: str
    intent_id: str
    timestamp: str
    target: Target = Field(discriminator=None)
    status: str
    value: float | str
    source_rule: str | None = None
    source: Literal["engine", "manual"]


# ── Contract 3c — Action Request ──────────────────────────────────────────────

class ActionRequest(BaseModel):
    """Invoke a parameterless abstract action on Unity. No target = scene-level."""
    model_config = {"extra": "forbid"}
    schema_version: str
    intent_id: str
    timestamp: str
    action: str
    target: Target | None = None
    source_rule: str | None = None
    source: Literal["engine", "manual"]


# ── Contract 3b — Object-Status Manifest ─────────────────────────────────────

class StatusDeclaration(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    type: Literal["discrete", "continuous"]
    values: list[str] | None = None
    range: dict[str, float] | None = None


class ObjectDeclaration(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    tags: list[str]
    statuses: list[StatusDeclaration]


class ObjectStatusManifest(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: str
    scene: str
    runtime: str
    objects: list[ObjectDeclaration]
    abstract_actions: list[dict[str, object]] = Field(default_factory=list)


# ── Runtime events (published on the event bus) ───────────────────────────────

class SampleEvent(BaseModel):
    """One sample frame from the signal pipeline."""
    model_config = {"extra": "forbid"}
    stream_name: str
    timestamp: float  # LSL clock time
    values: dict[str, float | str]  # channel name → value


class StaleEvent(BaseModel):
    """Emitted when no sample has arrived within stale_timeout_s."""
    model_config = {"extra": "forbid"}
    stream_name: str
    age_s: float  # seconds since last sample


class LinkStatusEvent(BaseModel):
    """Network link state change for any of the three links."""
    model_config = {"extra": "forbid"}
    link: Literal["sensor-pipeline", "unity-ws", "browser-ws"]
    state: Literal["up", "down", "stale", "reconnecting"]
    detail: str | None = None


class WarningEvent(BaseModel):
    """Generic warning surfaced to the dashboard."""
    model_config = {"extra": "forbid"}
    source: str
    message: str


# ── Contract 4 — VR Context (Unity → backend) ────────────────────────────────

class VrContextEvent(BaseModel):
    """Free-form study/scene context pushed by Unity on each step change.

    `fields` is an open map of label → scalar value; the dashboard renders
    whatever keys arrive, so any scene can describe its own context without a
    fixed schema. `ts` is the optional Unity-supplied timestamp.
    """
    model_config = {"extra": "forbid"}
    fields: dict[str, str | float | int | bool]
    ts: float | None = None
