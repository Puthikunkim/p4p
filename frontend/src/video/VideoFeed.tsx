/**
 * VideoFeed — subscribes to the V-CORE WebRTC signaling broker, accepts the
 * Unity publisher's offer, renders the remote video stream, and (when a
 * session is active) records it locally via MediaRecorder for upload.
 *
 * Data flow (browser is always the subscriber / receiver):
 *   Unity publisher → SDP offer → SignalingBroker → VideoFeed
 *   VideoFeed → SDP answer → SignalingBroker → Unity publisher
 *   Unity publisher --[WebRTC media]--> VideoFeed <video>
 */
import { useEffect, useRef, useState } from 'react'
import { SignalingClient } from './signaling'

interface Props {
  sessionId: string | null
}

type FeedStatus = 'idle' | 'connecting' | 'live' | 'recording' | 'error'

export function VideoFeed({ sessionId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const sigRef = useRef<SignalingClient | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [status, setStatus] = useState<FeedStatus>('idle')

  // ── boot / teardown ──────────────────────────────────────────────────────────

  useEffect(() => {
    const signalingUrl =
      window.location.protocol === 'https:'
        ? `wss://${window.location.host}/ws/signaling`
        : `ws://${window.location.host}/ws/signaling`

    const sig = new SignalingClient(signalingUrl)
    sigRef.current = sig

    sig.onPublisherAvailable = () => {
      // The publisher is already connected — initiate the offer/answer exchange
      // by creating a new RTCPeerConnection and waiting for their offer.
      // (publisher sends the offer; browser answers)
    }

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

    sig.onIce = (candidate, _peerId) => {
      pcRef.current?.addIceCandidate(candidate).catch(() => null)
    }

    setStatus('connecting')
    sig.connect().catch(() => setStatus('error'))

    return () => {
      teardownPeer()
      sig.disconnect()
      sigRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── start recording when session becomes active ───────────────────────────

  useEffect(() => {
    if (!sessionId) {
      stopRecording()
      return
    }
    const stream = videoRef.current?.srcObject
    if (stream instanceof MediaStream && stream.active) {
      startRecording(sessionId, stream)
    }
  }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── helpers ──────────────────────────────────────────────────────────────────

  function buildPeerConnection(publisherPeerId: string): RTCPeerConnection {
    teardownPeer()
    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
    pcRef.current = pc

    pc.onicecandidate = (ev) => {
      if (ev.candidate) {
        sigRef.current?.sendIce(ev.candidate.toJSON(), publisherPeerId)
      }
    }

    pc.ontrack = (ev) => {
      if (videoRef.current) {
        const stream = ev.streams[0]
        videoRef.current.srcObject = stream
        setStatus(sessionId ? 'recording' : 'live')
        if (sessionId) startRecording(sessionId, stream)
      }
    }

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
        teardownPeer()
        setStatus('idle')
      }
    }

    return pc
  }

  function teardownPeer() {
    stopRecording()
    pcRef.current?.close()
    pcRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }

  function startRecording(sid: string, stream: MediaStream) {
    if (recorderRef.current) return
    chunksRef.current = []
    const recorder = new MediaRecorder(stream, { mimeType: 'video/webm' })
    recorderRef.current = recorder

    // Capture LSL timestamp at recording start for alignment
    fetch(`/api/sessions/${sid}/video-start`, { method: 'POST' }).catch(() => null)

    recorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data)
    }

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'video/webm' })
      chunksRef.current = []
      uploadVideo(sid, blob)
    }

    recorder.start(1000) // 1 s chunks
    setStatus('recording')
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop()
    }
    recorderRef.current = null
  }

  function uploadVideo(sid: string, blob: Blob) {
    fetch(`/api/sessions/${sid}/video`, {
      method: 'POST',
      headers: { 'content-type': 'video/webm' },
      body: blob,
    }).catch(() => null)
  }

  // ── render ───────────────────────────────────────────────────────────────────

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
