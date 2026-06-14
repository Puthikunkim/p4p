import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { SignalingClient } from './signaling'
import { useVCoreStore } from '../ws/store'
import { VideoSessionContext, type FeedStatus } from './videoSession'

/**
 * Owns the single WebRTC subscription and the MediaRecorder for the whole app,
 * so a session keeps recording no matter which screen is showing. Mounted once
 * at the App root; the Session Monitor's <VideoFeed> just displays the shared
 * stream. (Unity's WebRtcSender is a single-peer publisher, so there can only be
 * one subscription — hence one persistent owner rather than per-screen ones.)
 */
export function VideoSessionProvider({ children }: { children: ReactNode }) {
  const sessionId = useVCoreStore((s) => s.activeSessionId)

  const [stream, setStream] = useState<MediaStream | null>(null)
  const [status, setStatus] = useState<FeedStatus>('idle')

  const pcRef = useRef<RTCPeerConnection | null>(null)
  const sigRef = useRef<SignalingClient | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const sessionIdRef = useRef<string | null>(null)

  // Keep the latest session id readable inside the once-built ontrack handler.
  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])

  const uploadVideo = useCallback((sid: string, blob: Blob) => {
    fetch(`/api/sessions/${sid}/video`, {
      method: 'POST',
      headers: { 'content-type': 'video/webm' },
      body: blob,
    }).catch(() => null)
  }, [])

  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    recorderRef.current = null
  }, [])

  const startRecording = useCallback((sid: string, src: MediaStream) => {
    if (recorderRef.current) return
    chunksRef.current = []
    const recorder = new MediaRecorder(src, { mimeType: 'video/webm' })
    recorderRef.current = recorder

    fetch(`/api/sessions/${sid}/video-start`, { method: 'POST' }).catch(() => null)

    recorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'video/webm' })
      chunksRef.current = []
      uploadVideo(sid, blob)
    }
    recorder.start(1000)
    setStatus('recording')
  }, [uploadVideo])

  const teardownPeer = useCallback(() => {
    stopRecording()
    pcRef.current?.close()
    pcRef.current = null
    streamRef.current = null
    setStream(null)
  }, [stopRecording])

  const buildPeerConnection = useCallback((publisherPeerId: string): RTCPeerConnection => {
    teardownPeer()
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
    pcRef.current = pc

    pc.onicecandidate = (ev) => {
      if (ev.candidate) sigRef.current?.sendIce(ev.candidate.toJSON(), publisherPeerId)
    }

    pc.ontrack = (ev) => {
      const src = ev.streams[0] ?? new MediaStream([ev.track])
      streamRef.current = src
      setStream(src)
      const sid = sessionIdRef.current
      if (sid) startRecording(sid, src)
      else setStatus('live')
    }

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
        teardownPeer()
        setStatus('idle')
      }
    }

    return pc
  }, [teardownPeer, startRecording])

  // Connect signaling once, for the app's lifetime.
  useEffect(() => {
    const signalingUrl =
      window.location.protocol === 'https:'
        ? `wss://${window.location.host}/ws/signaling`
        : `ws://${window.location.host}/ws/signaling`

    const sig = new SignalingClient(signalingUrl)
    sigRef.current = sig

    sig.onPublisherGone = () => {
      teardownPeer()
      setStatus('idle')
    }

    sig.onOffer = async (sdp, publisherPeerId) => {
      setStatus('connecting')
      const pc = buildPeerConnection(publisherPeerId)
      await pc.setRemoteDescription({ type: 'offer', sdp })
      const answer = await pc.createAnswer()
      await pc.setLocalDescription(answer)
      sig.sendAnswer(answer.sdp!, publisherPeerId)
    }

    sig.onIce = (candidate) => {
      pcRef.current?.addIceCandidate(candidate).catch(() => null)
    }

    sig.connect().catch(() => setStatus('error'))

    return () => {
      teardownPeer()
      sig.disconnect()
      sigRef.current = null
    }
  }, [teardownPeer, buildPeerConnection])

  // Start/stop recording as the active session changes (the stream may already be live).
  useEffect(() => {
    if (!sessionId) {
      stopRecording()
      if (streamRef.current) setStatus('live')
      return
    }
    const src = streamRef.current
    if (src && src.active) startRecording(sessionId, src)
  }, [sessionId, stopRecording, startRecording])

  return (
    <VideoSessionContext.Provider value={{ stream, status }}>
      {children}
    </VideoSessionContext.Provider>
  )
}
