"""Write signal samples to XDF (Extensible Data Format) files.

Only scalar and timeseries channels are written; categorical channels are silently
skipped (they are captured in SQLite instead).
"""
from __future__ import annotations

import struct
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from vcore.core.models import SampleEvent, SignalManifest

_CHANNEL_FORMAT = "double64"
_FORMAT_SIZE = 8  # bytes per double64 value


def _write_varlen_int(f: IO[bytes], n: int) -> None:
    """Write XDF variable-length integer (num_bytes prefix + value)."""
    if n < 256:
        f.write(struct.pack("<BB", 1, n))
    elif n < 2**32:
        f.write(struct.pack("<BI", 4, n))
    else:
        f.write(struct.pack("<BQ", 8, n))


def _write_chunk(f: IO[bytes], tag: int, content: bytes) -> None:
    payload = struct.pack("<H", tag) + content
    _write_varlen_int(f, len(payload))
    f.write(payload)


class XdfWriter:
    """Writes one XDF stream per recording session."""

    def __init__(self, path: Path, manifest: SignalManifest, stream_id: int = 1) -> None:
        self._path = path
        self._manifest = manifest
        self._stream_id = stream_id
        self._channels = [c for c in manifest.channels if c.type in ("scalar", "timeseries")]
        self._ch_names = [c.name for c in self._channels]
        self._n_channels = len(self._channels)
        self._n_samples = 0
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        self._f: IO[bytes] | None = None

    @property
    def has_numeric_channels(self) -> bool:
        return self._n_channels > 0

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self._path, "wb")  # noqa: SIM115
        self._f.write(b"XDF:")
        self._write_file_header()
        self._write_stream_header()

    def write_sample(self, event: SampleEvent) -> None:
        if self._f is None or self._n_channels == 0:
            return
        ts = event.timestamp
        if self._first_ts is None:
            self._first_ts = ts
        self._last_ts = ts

        values = [
            float(v) if isinstance(v, (int, float)) else 0.0
            for v in (event.values.get(n, 0.0) for n in self._ch_names)
        ]
        content = (
            struct.pack("<I", self._stream_id)  # stream_id
            + struct.pack("<BB", 1, 1)          # num_samples as varlen_int: nbytes=1, value=1
            + struct.pack("<B", 8)              # timestamp present
            + struct.pack("<d", ts)
            + struct.pack(f"<{self._n_channels}d", *values)
        )
        _write_chunk(self._f, 3, content)
        self._n_samples += 1

    def close(self) -> None:
        if self._f is None:
            return
        self._write_stream_footer()
        self._f.close()
        self._f = None

    # ── private helpers ───────────────────────────────────────────────────────

    def _write_file_header(self) -> None:
        xml = (
            '<?xml version="1.0"?><info><version>1.0</version>'
            f"<created_at>{datetime.now(UTC).isoformat()}</created_at>"
            "</info>"
        )
        _write_chunk(self._f, 1, xml.encode())  # type: ignore[arg-type]

    def _write_stream_header(self) -> None:
        ch_xml = "".join(
            f"<channel><label>{c.name}</label><unit>{c.unit}</unit>"
            f"<type>{c.type}</type></channel>"
            for c in self._channels
        )
        xml = (
            '<?xml version="1.0"?><info>'
            f"<name>{self._manifest.stream.name}</name>"
            "<type>Misc</type>"
            f"<channel_count>{self._n_channels}</channel_count>"
            f"<nominal_srate>{self._manifest.stream.nominal_srate}</nominal_srate>"
            f"<channel_format>{_CHANNEL_FORMAT}</channel_format>"
            f"<source_id>{self._manifest.stream.source_id}</source_id>"
            "<version>1.1</version>"
            f"<uid>{uuid.uuid4()}</uid>"
            f"<created_at>{datetime.now(UTC).isoformat()}</created_at>"
            f"<desc><channels>{ch_xml}</channels></desc>"
            "</info>"
        )
        content = struct.pack("<I", self._stream_id) + xml.encode()
        _write_chunk(self._f, 2, content)  # type: ignore[arg-type]

    def _write_stream_footer(self) -> None:
        xml = (
            '<?xml version="1.0"?><info>'
            f"<first_timestamp>{self._first_ts or 0.0}</first_timestamp>"
            f"<last_timestamp>{self._last_ts or 0.0}</last_timestamp>"
            f"<sample_count>{self._n_samples}</sample_count>"
            "</info>"
        )
        content = struct.pack("<I", self._stream_id) + xml.encode()
        _write_chunk(self._f, 6, content)  # type: ignore[arg-type]
