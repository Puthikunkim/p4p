// Display metadata for the three V-CORE connectivity links. Keyed by the wire
// key the backend emits on `link_status` events. Vendor-neutral by design — the
// signal pipeline is just "Sensor Pipeline", not tied to any one vendor.

export const LINK_LABELS: Record<string, string> = {
  'sensor-pipeline': 'Sensor Pipeline',
  'unity-ws': 'Unity WS',
  'browser-ws': 'Browser WS',
}

// Canonical display order for the status strips.
export const LINK_ORDER = ['sensor-pipeline', 'unity-ws', 'browser-ws'] as const

export function linkLabel(key: string): string {
  return LINK_LABELS[key] ?? key
}
