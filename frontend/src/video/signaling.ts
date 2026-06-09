/**
 * Thin WebSocket client for the V-CORE signaling broker.
 *
 * A browser dashboard is always a *subscriber*: it receives video from the
 * Unity publisher (or a mock) and never sends media itself.
 *
 * Usage:
 *   const sig = new SignalingClient('/ws/signaling')
 *   sig.onOffer   = async (sdp, peerId) => { ... }
 *   sig.onIce     = (candidate, peerId) => { ... }
 *   sig.onGone    = () => { ... }
 *   await sig.connect()
 *   // later:
 *   sig.sendAnswer(sdp, peerId)
 *   sig.sendIce(candidate)
 *   sig.disconnect()
 */

export type IceCandidate = RTCIceCandidateInit

export class SignalingClient {
  onOffer: ((sdp: string, peerId: string) => void) | null = null
  onAnswer: ((sdp: string) => void) | null = null
  onIce: ((candidate: IceCandidate, peerId: string) => void) | null = null
  onPublisherAvailable: (() => void) | null = null
  onPublisherGone: (() => void) | null = null

  private ws: WebSocket | null = null
  private peerId: string | null = null
  private readonly url: string

  constructor(url: string) {
    this.url = url
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url)
      this.ws = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ role: 'subscriber' }))
      }

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data as string) as Record<string, unknown>
        switch (msg.type) {
          case 'registered':
            this.peerId = msg.peer_id as string
            resolve()
            break
          case 'publisher-available':
            this.onPublisherAvailable?.()
            break
          case 'publisher-gone':
            this.onPublisherGone?.()
            break
          case 'offer':
            this.onOffer?.(msg.sdp as string, msg.peer_id as string)
            break
          case 'answer':
            this.onAnswer?.(msg.sdp as string)
            break
          case 'ice-candidate':
            this.onIce?.(msg.candidate as IceCandidate, msg.peer_id as string)
            break
        }
      }

      ws.onerror = () => reject(new Error('Signaling WebSocket error'))
      ws.onclose = () => {
        this.ws = null
        this.peerId = null
      }
    })
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
    this.peerId = null
  }

  sendOffer(sdp: string) {
    this._send({ type: 'offer', sdp })
  }

  sendAnswer(sdp: string, peerId: string) {
    this._send({ type: 'answer', sdp, peer_id: peerId })
  }

  sendIce(candidate: IceCandidate, peerId?: string) {
    this._send({ type: 'ice-candidate', candidate, ...(peerId ? { peer_id: peerId } : {}) })
  }

  get localPeerId(): string | null {
    return this.peerId
  }

  private _send(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }
}
