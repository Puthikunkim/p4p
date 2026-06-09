import { describe, it, expect, beforeEach } from 'vitest'
import { useVCoreStore } from './store'
import type { ServerMessage } from './store'

function fresh() {
  useVCoreStore.setState({
    signalManifest: null,
    objectStatusManifest: null,
    latestValues: {},
    history: {},
    rules: [],
    disabledRules: {},
    warnings: [],
    linkStatuses: {},
    wsState: 'disconnected',
  })
}

function apply(msg: ServerMessage) {
  useVCoreStore.getState().applyMessage(msg)
}

beforeEach(fresh)

describe('signal_manifest', () => {
  it('stores the manifest', () => {
    const manifest = {
      schema_version: '1.0.0',
      stream: { name: 's', source_id: 'x', nominal_srate: 10 },
      channels: [],
    } as ServerMessage extends { type: 'signal_manifest'; payload: infer P } ? P : never
    apply({ type: 'signal_manifest', payload: manifest })
    expect(useVCoreStore.getState().signalManifest).toBe(manifest)
  })
})

describe('object_status_manifest', () => {
  it('stores the manifest', () => {
    const manifest = { schema_version: '1.0.0', objects: [] } as never
    apply({ type: 'object_status_manifest', payload: manifest })
    expect(useVCoreStore.getState().objectStatusManifest).toBe(manifest)
  })
})

describe('sample', () => {
  it('updates latestValues', () => {
    apply({ type: 'sample', payload: { stream_name: 's', timestamp: 1.0, values: { alpha: 0.5 } } })
    expect(useVCoreStore.getState().latestValues['alpha']).toBe(0.5)
  })

  it('appends numeric values to history', () => {
    apply({ type: 'sample', payload: { stream_name: 's', timestamp: 1.0, values: { alpha: 0.5 } } })
    apply({ type: 'sample', payload: { stream_name: 's', timestamp: 2.0, values: { alpha: 0.7 } } })
    const hist = useVCoreStore.getState().history['alpha']
    expect(hist).toHaveLength(2)
    expect(hist[0]).toEqual([1.0, 0.5])
    expect(hist[1]).toEqual([2.0, 0.7])
  })

  it('does not add string values to history', () => {
    apply({ type: 'sample', payload: { stream_name: 's', timestamp: 1.0, values: { mood: 'calm' } } })
    expect(useVCoreStore.getState().history['mood']).toBeUndefined()
    expect(useVCoreStore.getState().latestValues['mood']).toBe('calm')
  })

  it('caps history at MAX_HISTORY=300', () => {
    for (let i = 0; i < 310; i++) {
      apply({ type: 'sample', payload: { stream_name: 's', timestamp: i, values: { x: i } } })
    }
    const hist = useVCoreStore.getState().history['x']
    expect(hist.length).toBe(300)
    expect(hist[0][0]).toBe(10)
  })
})

describe('warning', () => {
  it('prepends warnings', () => {
    apply({ type: 'warning', payload: { source: 'engine', message: 'a' } })
    apply({ type: 'warning', payload: { source: 'engine', message: 'b' } })
    const { warnings } = useVCoreStore.getState()
    expect(warnings[0].message).toBe('b')
    expect(warnings[1].message).toBe('a')
  })

  it('clearWarnings empties array', () => {
    apply({ type: 'warning', payload: { source: 'x', message: 'w' } })
    useVCoreStore.getState().clearWarnings()
    expect(useVCoreStore.getState().warnings).toHaveLength(0)
  })
})

describe('link_status', () => {
  it('stores status keyed by link name', () => {
    apply({ type: 'link_status', payload: { link: 'om-lsl', state: 'up' } })
    const ls = useVCoreStore.getState().linkStatuses['om-lsl']
    expect(ls.state).toBe('up')
  })
})

describe('rule_list', () => {
  it('stores rules and disabled map', () => {
    const rule = {
      id: 'r1',
      schema_version: '1.0.0',
      enabled: true,
      when: { all: [{ signal: 'x', op: '>=' as const, threshold: 0.5 }] as never} ,
      then: { set: { target: { tag: 't' }, status: 's', value: 1 } },
    } as never
    apply({ type: 'rule_list', payload: { rules: [rule], disabled: { r2: 'no signal' } } })
    const { rules, disabledRules } = useVCoreStore.getState()
    expect(rules).toHaveLength(1)
    expect(rules[0].id).toBe('r1')
    expect(disabledRules['r2']).toBe('no signal')
  })
})

describe('wsState', () => {
  it('setWsState updates state', () => {
    useVCoreStore.getState().setWsState('connected')
    expect(useVCoreStore.getState().wsState).toBe('connected')
  })
})
