"""Store session video files on disk."""
from __future__ import annotations

from pathlib import Path


class VideoStore:
    """Saves video blobs to per-session directories."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def save_video(
        self,
        session_id: str,
        content: bytes,
        content_type: str = "video/webm",
    ) -> Path:
        ext = ".webm" if "webm" in content_type else ".mp4"
        path = self._data_dir / session_id / f"video{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path
