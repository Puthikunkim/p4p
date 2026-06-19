import { useEffect, useState, type ReactNode } from 'react'
import { Room, RoomEvent, Track, type RemoteTrack } from 'livekit-client'
import { VideoSessionContext, type FeedStatus } from './videoSession'

/**
 * Subscribes to the shared LiveKit room and exposes the participant's spectator
 * video to the app. Recording is handled **server-side** by LiveKit Egress
 * (started by the backend on session start), so the browser only *views* the
 * mirror here — it no longer records or uploads.
 *
 * Mounted once at the App root; the Session Monitor's <VideoFeed> displays the
 * shared stream. Video appears whenever the Unity publisher is in the room.
 * If LiveKit is disabled (token endpoint returns 409) the app still runs with no
 * mirror.
 */
export function VideoSessionProvider({ children }: { children: ReactNode }) {
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [status, setStatus] = useState<FeedStatus>('idle')

  useEffect(() => {
    let room: Room | null = null
    let cancelled = false

    const attachVideo = (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Video) {
        setStream(new MediaStream([track.mediaStreamTrack]))
        setStatus('live')
      }
    }

    async function connect() {
      setStatus('connecting')
      let token: string
      let url: string
      try {
        const identity = `dashboard-${Math.random().toString(36).slice(2, 8)}`
        const resp = await fetch(`/api/livekit/token?identity=${identity}&role=subscriber`)
        if (!resp.ok) {
          setStatus('idle') // LiveKit disabled (409) or backend unavailable
          return
        }
        ;({ token, url } = (await resp.json()) as { token: string; url: string })
      } catch {
        setStatus('idle')
        return
      }

      const r = new Room()
      room = r
      r.on(RoomEvent.TrackSubscribed, (track) => attachVideo(track))
        .on(RoomEvent.TrackUnsubscribed, () => {
          setStream(null)
          setStatus('idle')
        })
        .on(RoomEvent.Disconnected, () => {
          setStream(null)
          setStatus('idle')
        })

      try {
        await r.connect(url, token)
        if (cancelled) {
          await r.disconnect()
          return
        }
        // Attach any video track already published when we joined.
        let attached = false
        for (const participant of r.remoteParticipants.values()) {
          for (const pub of participant.trackPublications.values()) {
            if (pub.track && pub.track.kind === Track.Kind.Video) {
              attachVideo(pub.track)
              attached = true
            }
          }
        }
        if (!attached) setStatus('idle') // connected; waiting for the publisher
      } catch {
        setStatus('error')
      }
    }

    void connect()
    return () => {
      cancelled = true
      room?.disconnect()
    }
  }, []) // connect once for the app's lifetime

  return (
    <VideoSessionContext.Provider value={{ stream, status }}>
      {children}
    </VideoSessionContext.Provider>
  )
}
