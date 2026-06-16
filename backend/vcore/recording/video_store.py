"""Store session video files on disk."""
from __future__ import annotations

from pathlib import Path


class VideoStore:
    """Saves session video to a configurable directory, one file per session."""

    def __init__(self, video_dir: Path) -> None:
        self._video_dir = Path(video_dir)

    def save_video(
        self,
        session_id: str,
        content: bytes,
        content_type: str = "video/webm",
    ) -> Path:
        ext = ".webm" if "webm" in content_type else ".mp4"
        path = self._video_dir / f"{session_id}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path
