import { useEffect, useRef } from 'react'
import { useVideoSession } from './videoSession'

/**
 * Displays the shared spectator stream owned by <VideoSessionProvider>. The
 * WebRTC subscription and recording live in the provider, so navigating away
 * from this screen does NOT stop recording.
 */
export function VideoFeed() {
  const { stream, status } = useVideoSession()
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream
  }, [stream])

  return (
    <div className="video-feed">
      <div className="video-feed-header">
        <span className="video-feed-label">Video Mirror</span>
        <span className={`video-feed-status video-feed-status--${status}`}>{status}</span>
      </div>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className={`video-feed-player ${status === 'idle' ? 'video-feed-player--hidden' : ''}`}
      />
      {status === 'idle' && (
        <div className="video-feed-placeholder">Waiting for Unity publisher…</div>
      )}
    </div>
  )
}
