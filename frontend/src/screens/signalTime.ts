// Time-mapping for the recorded-signals review chart.
//
// Recorded signal samples carry LSL-clock timestamps; the session video carries a media
// timeline (seconds). To draw the signal cursor in sync with the video we map LSL-seconds
// → media-seconds using the per-session rate below.
//
// Two-point drift correction: with the start anchor (`video_lsl_ts`), the stop anchor
// (`video_lsl_ts_end`) and the video's own duration, the LSL-seconds-per-media-second rate
// is (anchorSpan / videoDuration) — ideally ≈ 1, off only by genuine clock drift.
//
// BUT the rate is only trustworthy when it is *close* to 1. A large mismatch means the
// recorded video is incomplete/corrupt — e.g. LiveKit egress can write a short/truncated
// WebM whose timeline ends well before the recording actually did. Dividing complete signal
// data by such a rate would wrongly *compress* the signals to match the broken video,
// hiding the back half of the session. In that case we fall back to 1:1 (anchor start only)
// so every recorded sample is still plotted on its true timeline.
const MAX_PLAUSIBLE_DRIFT = 0.25 // ±25% — generous for anchor latency on short sessions

export function signalTimeRate(
  videoLslTs: number | null,
  videoLslTsEnd: number | null,
  videoDuration: number,
): number {
  if (videoLslTs != null && videoLslTsEnd != null && videoDuration > 1) {
    const r = (videoLslTsEnd - videoLslTs) / videoDuration
    if (r >= 1 - MAX_PLAUSIBLE_DRIFT && r <= 1 + MAX_PLAUSIBLE_DRIFT) return r
  }
  return 1
}
