"""Phase 3 tests — ingestion (LSLSource)."""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

import pytest

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import LinkStatusEvent, SampleEvent
from vcore.core.schema import ActiveManifests
from vcore.ingestion.lsl_source import LSLSource

FIXTURES = Path(__file__).parent.parent.parent / "tools" / "fixtures"
MANIFEST = FIXTURES / "sample_session.manifest.json"


# ── LSL link-state watchdog (stale → down) ────────────────────────────────────

@pytest.mark.asyncio
async def test_lsl_watchdog_goes_down_after_prolonged_silence() -> None:
    """After a sample, silence first yields 'stale' then escalates to 'down'."""
    bus = EventBus()
    manifests = ActiveManifests()
    src = LSLSource(
        "sensor.cognitive",
        MANIFEST,
        bus=bus,
        manifests=manifests,
        stale_timeout_s=0.2,
        offline_timeout_s=0.5,
    )

    states: list[str] = []

    async def on_link(p: object) -> None:
        assert isinstance(p, LinkStatusEvent)
        states.append(p.state)

    bus.subscribe(Topics.LINK_STATUS, on_link)

    # Simulate a sample having just arrived, then run only the watchdog (no inlet).
    src._running = True
    src._last_sample_at = time.monotonic()
    task = asyncio.create_task(src._watchdog())
    await asyncio.sleep(1.5)
    src._running = False
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert "stale" in states
    assert states[-1] == "down"
    assert src.link_state == "down"


# ── LSL source (integration, skipped if LSL not available) ────────────────────

@pytest.mark.asyncio
async def test_lsl_source_resolves_and_reads() -> None:
    pylsl = pytest.importorskip("pylsl")

    info = pylsl.StreamInfo("sensor.cognitive.test", "EEG", 2, 20, pylsl.cf_float32, "test-src-unique")
    outlet = pylsl.StreamOutlet(info)

    # Minimal 2-channel manifest matching the outlet above (no categorical channel
    # — LSL float32 streams carry numeric values only).
    import json
    import tempfile
    manifest_data = {
        "schema_version": "1.0.0",
        "stream": {"name": "sensor.cognitive.test", "source_id": "test-src-unique", "nominal_srate": 20},
        "channels": [
            {"name": "cognitive_load", "unit": "normalized", "type": "scalar",
             "range": {"min": 0, "max": 1}, "display": {"hint": "stat_card", "label": "Cognitive Load"}},
            {"name": "eeg_alpha_power", "unit": "uV^2", "type": "timeseries",
             "range": {"min": 0, "max": 100}, "display": {"hint": "line_chart", "label": "Alpha Power"}},
        ],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(manifest_data, f)
        manifest_tmp = Path(f.name)

    bus = EventBus()
    manifests = ActiveManifests()
    src = LSLSource(
        "sensor.cognitive.test",
        manifest_tmp,
        bus=bus,
        manifests=manifests,
        stale_timeout_s=5.0,
        resolve_timeout=5.0,
    )

    samples: list[SampleEvent] = []

    async def on_sample(p: object) -> None:
        assert isinstance(p, SampleEvent)
        samples.append(p)

    bus.subscribe(Topics.SAMPLE, on_sample)

    # Push samples continuously in background while the inlet connects and reads.
    async def push_loop() -> None:
        for _ in range(40):
            outlet.push_sample([0.5, 25.0])
            await asyncio.sleep(0.05)

    await src.start()
    push_task = asyncio.create_task(push_loop())
    await asyncio.sleep(3.0)
    await src.stop()
    push_task.cancel()
    manifest_tmp.unlink(missing_ok=True)

    assert len(samples) >= 1
    assert set(samples[0].values.keys()) == {"cognitive_load", "eeg_alpha_power"}
