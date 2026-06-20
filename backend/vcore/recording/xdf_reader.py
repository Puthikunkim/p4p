"""Read recorded numeric signal samples back from a session's XDF (for review)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def load_xdf_signals(path: Path | str, max_points: int = 2000) -> dict[str, Any]:
    """Return the numeric signal series recorded in an XDF file.

    Shape::

        {"channels": ["cognitive_load", ...],
         "timestamps": [<lsl_clock>, ...],          # one per (decimated) sample
         "series": {"cognitive_load": [<value>, ...], ...}}

    Timestamps are on the **LSL clock**, so the frontend aligns them to the video via the
    session's ``video_lsl_ts`` anchor. Decimated to at most *max_points* samples.
    """
    import pyxdf

    streams, _ = pyxdf.load_xdf(str(path))
    if not streams:
        return {"channels": [], "timestamps": [], "series": {}}

    stream = streams[0]
    timestamps_raw = stream.get("time_stamps", [])
    data = stream.get("time_series", [])

    names: list[str] = []
    try:
        channels = stream["info"]["desc"][0]["channels"][0]["channel"]
        names = [c["label"][0] for c in channels]
    except (KeyError, IndexError, TypeError):
        names = []

    n = len(timestamps_raw)
    if n == 0:
        return {"channels": names, "timestamps": [], "series": {nm: [] for nm in names}}

    step = max(1, n // max_points)
    idx = range(0, n, step)
    timestamps = [float(timestamps_raw[i]) for i in idx]
    series = {nm: [float(data[i][ci]) for i in idx] for ci, nm in enumerate(names)}
    return {"channels": names, "timestamps": timestamps, "series": series}
