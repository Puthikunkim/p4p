"""Multi-stream ingestion: signal-manifest channel union, per-stream link ids,
and NaN→null JSON sanitisation (the sensor-pipeline dual-stream integration)."""
from __future__ import annotations

import json

from vcore.bridge.ws import _dumps, _json_sanitise
from vcore.core.eventbus import EventBus
from vcore.core.schema import ActiveManifests
from vcore.ingestion.lsl_source import LSLSource


def _manifest(name: str, channels: list[dict]) -> dict:
    return {
        "schema_version": "1.0.0",
        "stream": {"name": name, "source_id": "om-pipeline", "nominal_srate": 2.0},
        "channels": channels,
    }


def _cat(name: str, categories: list[str]) -> dict:
    return {
        "name": name, "unit": "class", "type": "categorical",
        "categories": categories, "display": {"hint": "quadrant", "label": name},
    }


def _num(name: str) -> dict:
    return {
        "name": name, "unit": "u", "type": "timeseries",
        "range": {"min": 0, "max": 1}, "display": {"hint": "line_chart", "label": name},
    }


def test_signal_manifest_unions_channels_across_streams() -> None:
    m = ActiveManifests()
    m.update_signal_manifest(_manifest("sensor.predictions", [_cat("emotion", ["0", "1"]), _cat("cognitive_load", ["Low", "High"])]))
    m.update_signal_manifest(_manifest("sensor.physiological", [_num("heart_rate"), _num("hrv_rmssd")]))

    merged = m.signal_manifest
    assert merged is not None
    assert [c["name"] for c in merged["channels"]] == ["emotion", "cognitive_load", "heart_rate", "hrv_rmssd"]
    # Representative stream header is the first registered stream.
    assert merged["stream"]["name"] == "sensor.predictions"


def test_signal_manifest_dedups_channel_names_first_wins() -> None:
    m = ActiveManifests()
    m.update_signal_manifest(_manifest("s1", [_num("shared")]))
    m.update_signal_manifest(_manifest("s2", [_num("shared"), _num("only2")]))
    assert [c["name"] for c in m.signal_manifest["channels"]] == ["shared", "only2"]


def test_updating_one_stream_keeps_the_other() -> None:
    m = ActiveManifests()
    m.update_signal_manifest(_manifest("s1", [_num("a")]))
    m.update_signal_manifest(_manifest("s2", [_num("b")]))
    # Re-send s1 with an extra channel; s2 must remain in the union.
    m.update_signal_manifest(_manifest("s1", [_num("a"), _num("a2")]))
    assert [c["name"] for c in m.signal_manifest["channels"]] == ["a", "a2", "b"]


def test_no_streams_yields_none() -> None:
    assert ActiveManifests().signal_manifest is None


def test_lsl_source_derives_per_stream_link_id() -> None:
    src = LSLSource(stream_name="sensor.physiological", manifest_path="x.json", bus=EventBus(), manifests=ActiveManifests())
    assert src.link_id == "sensor-pipeline:sensor.physiological"


def test_json_sanitise_converts_nan_and_inf_to_null() -> None:
    payload = {"values": {"heart_rate": float("nan"), "hrv": 42.0, "eda": float("inf")}}
    assert _json_sanitise(payload) == {"values": {"heart_rate": None, "hrv": 42.0, "eda": None}}
    # The dumped string is valid JSON (no bare NaN token) and round-trips to null.
    parsed = json.loads(_dumps(payload))
    assert parsed["values"]["heart_rate"] is None
    assert parsed["values"]["hrv"] == 42.0
