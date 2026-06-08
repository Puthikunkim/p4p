import { useVCoreStore, type ServerMessage } from './store'

const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 16_000

let ws: WebSocket | null = null
let reconnectDelay = RECONNECT_BASE_MS
let stopped = false

export function connectDashboard(url: string): void {
  stopped = false
  _connect(url)
}

export function disconnectDashboard(): void {
  stopped = true
  ws?.close()
  ws = null
}

function _connect(url: string): void {
  const { setWsState, applyMessage } = useVCoreStore.getState()
  setWsState('connecting')

  const socket = new WebSocket(url)
  ws = socket

  socket.onopen = () => {
    reconnectDelay = RECONNECT_BASE_MS
    setWsState('connected')
  }

  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as ServerMessage
      applyMessage(msg)
    } catch {
      // ignore malformed frames
    }
  }

  socket.onclose = () => {
    ws = null
    setWsState('disconnected')
    if (!stopped) {
      setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
        _connect(url)
      }, reconnectDelay)
    }
  }

  socket.onerror = () => {
    socket.close()
  }
}
