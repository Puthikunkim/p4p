import { create } from 'zustand'
import type { SignalSchemaContract1, Channel } from '../contracts/SignalSchema'
import type { ObjectStatusManifestContract3B } from '../contracts/ObjectStatusManifest'
import type { RuleGrammarContract2 } from '../contracts/RuleGrammar'

export interface LinkStatus {
  link: string
  state: 'up' | 'down' | 'stale' | 'reconnecting'
  detail?: string
}

export interface Warning {
  source: string
  message: string
  at: number  // Date.now()
}

export interface VrContext {
  fields: Record<string, string | number | boolean>
  at: number  // Date.now() when received
}

export interface VCoreStore {
  // manifests
  signalManifest: SignalSchemaContract1 | null
  objectStatusManifest: ObjectStatusManifestContract3B | null
  // live values: channel name → latest sample value
  latestValues: Record<string, number | string>
  // history: channel name → circular buffer of [timestamp, value] pairs
  history: Record<string, [number, number][]>
  // rules
  rules: RuleGrammarContract2[]
  disabledRules: Record<string, string>
  // system
  warnings: Warning[]      // genuine warnings (stale signal, dropped request, …)
  adaptations: Warning[]   // rule firings (engine + manual)
  linkStatuses: Record<string, LinkStatus>
  vrContext: VrContext | null
  wsState: 'connecting' | 'connected' | 'disconnected'
  // session
  activeSessionId: string | null

  // actions
  applyMessage: (msg: ServerMessage) => void
  setWsState: (state: VCoreStore['wsState']) => void
  clearLinkStatuses: () => void
  clearWarnings: () => void
  clearAdaptations: () => void
  setActiveSession: (id: string | null) => void
}

export type ServerMessage =
  | { type: 'signal_manifest'; payload: SignalSchemaContract1 }
  | { type: 'object_status_manifest'; payload: ObjectStatusManifestContract3B }
  | { type: 'sample'; payload: { stream_name: string; timestamp: number; values: Record<string, number | string> } }
  | { type: 'warning'; payload: { source: string; message: string } }
  | { type: 'link_status'; payload: { link: string; state: string; detail?: string } }
  | { type: 'rule_list'; payload: { rules: RuleGrammarContract2[]; disabled: Record<string, string> } }
  | { type: 'rule_fired'; payload: { source_rule?: string; source: string; status: string; value: unknown; target: unknown } }
  | { type: 'vr_context'; payload: { fields: Record<string, string | number | boolean>; ts?: number | null } }

const MAX_HISTORY = 300  // samples per channel

export const useVCoreStore = create<VCoreStore>((set) => ({
  signalManifest: null,
  objectStatusManifest: null,
  latestValues: {},
  history: {},
  rules: [],
  disabledRules: {},
  warnings: [],
  adaptations: [],
  linkStatuses: {},
  vrContext: null,
  wsState: 'disconnected',
  activeSessionId: null,

  applyMessage: (msg) =>
    set((state) => {
      switch (msg.type) {
        case 'signal_manifest':
          return { signalManifest: msg.payload }

        case 'object_status_manifest':
          return { objectStatusManifest: msg.payload }

        case 'sample': {
          const newLatest = { ...state.latestValues, ...msg.payload.values }
          const newHistory = { ...state.history }
          for (const [ch, val] of Object.entries(msg.payload.values)) {
            if (typeof val !== 'number') continue
            const prev = newHistory[ch] ?? []
            const next: [number, number][] = [...prev, [msg.payload.timestamp, val]]
            newHistory[ch] = next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next
          }
          return { latestValues: newLatest, history: newHistory }
        }

        case 'warning': {
          const w: Warning = { ...msg.payload, at: Date.now() }
          return { warnings: [w, ...state.warnings].slice(0, 50) }
        }

        case 'link_status': {
          const ls = msg.payload as LinkStatus
          return { linkStatuses: { ...state.linkStatuses, [ls.link]: ls } }
        }

        case 'vr_context':
          return { vrContext: { fields: msg.payload.fields, at: Date.now() } }

        case 'rule_list':
          return { rules: msg.payload.rules, disabledRules: msg.payload.disabled }

        case 'rule_fired': {
          const p = msg.payload
          const ruleLabel = p.source_rule ?? p.source
          const target = typeof p.target === 'object' && p.target !== null
            ? ('tag' in p.target ? `tag:${(p.target as {tag:string}).tag}` : `id:${(p.target as {id:string}).id}`)
            : String(p.target)
          const w: Warning = {
            source: ruleLabel,
            message: `${p.status} → ${p.value} on ${target}${p.source === 'manual' ? ' (manual)' : ''}`,
            at: Date.now(),
          }
          return { adaptations: [w, ...state.adaptations].slice(0, 50) }
        }

        default:
          return {}
      }
    }),

  setWsState: (wsState) => set({ wsState }),

  clearLinkStatuses: () => set({ linkStatuses: {} }),

  clearWarnings: () => set({ warnings: [] }),

  clearAdaptations: () => set({ adaptations: [] }),

  setActiveSession: (id) => set({ activeSessionId: id }),
}))

const EMPTY_CHANNELS: Channel[] = []

// Convenience selector: channels from the active signal manifest
export function useChannels(): Channel[] {
  return useVCoreStore((s) => s.signalManifest?.channels ?? EMPTY_CHANNELS)
}
