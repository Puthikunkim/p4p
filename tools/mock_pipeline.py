#!/usr/bin/env python3
"""Mock signal pipeline for hardware-free development.

Reads the fixture Signal Schema manifest and streams synthetic samples over
LSL at the manifest's nominal sample rate.  Signal values follow a slow sine
wave so rules with threshold conditions trigger naturally.

Usage
-----
    python tools/mock_pipeline.py
    python tools/mock_pipeline.py --manifest tools/fixtures/sample_session.manifest.json
    python tools/mock_pipeline.py --pattern ramp --rate 5
    python tools/mock_pipeline.py --scale 1.5   # amplitude multiplier

Requirements: pylsl + a running LSL runtime (liblsl on PATH / LD_LIBRARY_PATH).
Tip: V-CORE's ReplaySource (used in tests) works without LSL at all.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_MANIFEST = _ROOT / "tools" / "fixtures" / "full_session.manifest.json"
_CATEGORIES = ["calm", "stressed", "bored", "engaged"]
_CYCLE_S = 30.0  # full sine cycle length in seconds


def _make_value(channel: dict, t: float, scale: float, pattern: str) -> float | str:
    ch_type = channel.get("type", "scalar")
    name = channel.get("name", "")

    if ch_type == "categorical":
        # Cycle through categories every 8 s
        cats: list[str] = channel.get("categories", _CATEGORIES)
        idx = int(t / 8) % len(cats)
        return cats[idx]

    rng = channel.get("range", {})
    lo: float = rng.get("min", 0.0)
    hi: float = rng.get("max", 1.0)
    span = hi - lo

    if pattern == "sine":
        phase = (hash(name) % 100) / 100.0  # per-channel phase offset
        raw = 0.5 + 0.5 * math.sin(2 * math.pi * (t / _CYCLE_S + phase))
    elif pattern == "ramp":
        raw = (t % _CYCLE_S) / _CYCLE_S
    else:  # constant 0.9 — triggers most threshold rules
        raw = 0.9

    return lo + span * min(1.0, raw * scale)


def run(manifest_path: Path, rate: float, pattern: str, scale: float) -> None:
    try:
        import pylsl
    except ImportError:
        print(
            "[mock_pipeline] pylsl is not installed.\n"
            "  pip install pylsl\n"
            "  (or use ReplaySource in tests — no LSL runtime needed)",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest: dict = json.loads(manifest_path.read_text())
    stream_info = manifest["stream"]
    channels: list[dict] = manifest["channels"]

    # Only scalar/timeseries channels go into the LSL stream (categorical are string)
    numeric_chs = [c for c in channels if c.get("type") != "categorical"]
    categorical_chs = [c for c in channels if c.get("type") == "categorical"]

    stream_name: str = stream_info["name"]
    n_channels = len(numeric_chs) + len(categorical_chs)

    info = pylsl.StreamInfo(
        name=stream_name,
        type="mixed",
        channel_count=n_channels,
        nominal_srate=rate,
        channel_format=pylsl.cf_float32,
        source_id=stream_info.get("source_id", "mock-pipeline"),
    )

    all_channels = numeric_chs + categorical_chs
    chns = info.desc().append_child("channels")
    for ch in all_channels:
        chn = chns.append_child("channel")
        chn.append_child_value("label", ch["name"])
        chn.append_child_value("unit", ch.get("unit", ""))
        chn.append_child_value("type", ch.get("type", "scalar"))

    outlet = pylsl.StreamOutlet(info)
    interval = 1.0 / rate
    print(
        f"[mock_pipeline] streaming '{stream_name}' "
        f"at {rate} Hz ({n_channels} channels, pattern={pattern})",
        flush=True,
    )

    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            sample = [_make_value(ch, t, scale, pattern) for ch in all_channels]
            # Encode categoricals as integer index so LSLSource can decode them back
            encoded: list[float] = []
            for ch, v in zip(all_channels, sample):
                if isinstance(v, str):
                    cats: list[str] = ch.get("categories", [])
                    encoded.append(float(cats.index(v)) if v in cats else 0.0)
                else:
                    encoded.append(float(v))
            outlet.push_sample(encoded)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[mock_pipeline] stopped", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_DEFAULT_MANIFEST,
        help="Path to Signal Schema JSON manifest",
    )
    parser.add_argument(
        "--rate", type=float, default=10.0, help="Sample rate in Hz (default: 10)"
    )
    parser.add_argument(
        "--pattern",
        choices=["sine", "ramp", "high"],
        default="sine",
        help="Signal pattern: sine (default), ramp, or high (constant 0.9)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Amplitude multiplier (default: 1.0)",
    )
    args = parser.parse_args()
    run(args.manifest, args.rate, args.pattern, args.scale)


if __name__ == "__main__":
    main()
