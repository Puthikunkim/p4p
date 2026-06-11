"""Phase 3 tests — ingestion adapters."""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

import pytest

from vcore.core.eventbus import EventBus, Topics
from vcore.core.models import LinkStatusEvent, SampleEvent, StaleEvent
from vcore.core.schema import ActiveManifests
from vcore.ingestion.lsl_source import LSLSource
from vcore.ingestion.replay_source import ReplaySource

FIXTURES = Path(__file__).parent.parent.parent / "tools" / "fixtures"
MANIFEST = FIXTURES / "sample_session.manifest.json"
CSV = FIXTURES / "sample_session.csv"


def _make_source(*, loop: bool = False, stale_timeout_s: float = 5.0) -> tuple[ReplaySource, EventBus, ActiveManifests]:
    bus = EventBus()
    manifests = ActiveManifests()
    src = ReplaySource(MANIFEST, CSV, bus=bus, manifests=manifests, stale_timeout_s=stale_timeout_s, loop=loop)
    return src, bus, manifests


# ── manifest published ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_publishes_manifest_before_samples() -> None:
    src, bus, _ = _make_source()
    received: list[str] = []

    async def on_manifest(p: object) -> None:
        received.append("manifest")

    async def on_sample(p: object) -> None:
        received.append("sample")

    bus.subscribe(Topics.MANIFEST_UPDATED, on_manifest)
    bus.subscribe(Topics.SAMPLE, on_sample)

    await src.start()
    await asyncio.sleep(0.05)
    await src.stop()

    assert received[0] == "manifest"
    assert "sample" in received


# ── samples arrive ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_emits_correct_number_of_samples() -> None:
    src, bus, _ = _make_source(loop=False)
    samples: list[SampleEvent] = []

    async def on_sample(p: object) -> None:
        assert isinstance(p, SampleEvent)
        samples.append(p)

    bus.subscribe(Topics.SAMPLE, on_sample)
    await src.start()
    # 10 rows at 10 Hz = 1 s; wait 1.5 s to be sure all rows are consumed
    await asyncio.sleep(1.5)
    await src.stop()

    assert len(samples) == 10


@pytest.mark.asyncio
async def test_replay_sample_has_correct_channels() -> None:
    src, bus, _ = _make_source(loop=False)
    samples: list[SampleEvent] = []

    async def on_sample(p: object) -> None:
        assert isinstance(p, SampleEvent)
        samples.append(p)

    bus.subscribe(Topics.SAMPLE, on_sample)
    await src.start()
    await asyncio.sleep(0.2)
    await src.stop()

    assert len(samples) >= 1
    first = samples[0]
    assert set(first.values.keys()) == {"cognitive_load", "eeg_alpha_power", "affect"}
    assert isinstance(first.values["cognitive_load"], float)
    assert isinstance(first.values["affect"], str)


@pytest.mark.asyncio
async def test_replay_manifest_stored_in_registry() -> None:
    src, _, manifests = _make_source()
    await src.start()
    await asyncio.sleep(0.05)
    await src.stop()

    assert manifests.signal_manifest is not None
    assert manifests.signal_manifest["stream"]["name"] == "om.cognitive"


# ── stale detection ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_event_emitted_after_silence() -> None:
    src, bus, _ = _make_source(loop=False, stale_timeout_s=0.5)
    stale_events: list[StaleEvent] = []

    async def on_stale(p: object) -> None:
        assert isinstance(p, StaleEvent)
        stale_events.append(p)

    bus.subscribe(Topics.STALE, on_stale)

    await src.start()
    # All 10 rows play out in 1 s; wait for them to finish + watchdog fires
    await asyncio.sleep(2.5)
    await src.stop()

    assert len(stale_events) >= 1
    assert stale_events[0].stream_name == "om.cognitive"
    assert stale_events[0].age_s > 0.5


# ── LSL link-state watchdog (stale → down) ────────────────────────────────────

@pytest.mark.asyncio
async def test_lsl_watchdog_goes_down_after_prolonged_silence() -> None:
    """After a sample, silence first yields 'stale' then escalates to 'down'."""
    bus = EventBus()
    manifests = ActiveManifests()
    src = LSLSource(
        "om.cognitive",
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

    info = pylsl.StreamInfo("om.cognitive.test", "EEG", 2, 20, pylsl.cf_float32, "test-src-unique")
    outlet = pylsl.StreamOutlet(info)

    # Minimal 2-channel manifest matching the outlet above (no categorical channel
    # — LSL float32 streams carry numeric values only).
    import json
    import tempfile
    manifest_data = {
        "schema_version": "1.0.0",
        "stream": {"name": "om.cognitive.test", "source_id": "test-src-unique", "nominal_srate": 20},
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

    from vcore.ingestion.lsl_source import LSLSource

    bus = EventBus()
    manifests = ActiveManifests()
    src = LSLSource(
        "om.cognitive.test",
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
