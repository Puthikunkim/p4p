from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class ThenClause(BaseModel):
    model_config = {"extra": "forbid"}
    set: SetAction
    cooldown_s: float | None = None


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
