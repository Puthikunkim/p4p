// Display metadata for V-CORE connectivity links, keyed by the wire key the
// backend emits on `link_status` events. Vendor-neutral by design. The signal
// pipeline is split by role, so each ingested stream reports its own link as
// `sensor-pipeline:<stream>` (e.g. `sensor-pipeline:sensor.physiological`).

export const LINK_LABELS: Record<string, string> = {
  'sensor-pipeline': 'Sensor Pipeline',
  'unity-ws': 'Unity WS',
  'browser-ws': 'Browser WS',
}

// Fixed runtime links, shown after the (dynamic, per-stream) sensor links.
const RUNTIME_LINKS = ['unity-ws', 'browser-ws'] as const

export function linkLabel(key: string): string {
  if (key.startsWith('sensor-pipeline:')) {
    // "sensor-pipeline:sensor.physiological" → "Sensor: physiological"
    const stream = key.slice('sensor-pipeline:'.length).replace(/^sensor\./, '')
    return `Sensor: ${stream}`
  }
  return LINK_LABELS[key] ?? key
}

// Ordered link keys to display: one chip per sensor stream that has reported
// status (sorted), then the fixed runtime links. Sensor chips appear as soon as
// the connect snapshot pushes each stream's link status.
export function orderedLinkKeys(linkStatuses: Record<string, unknown>): string[] {
  const sensor = Object.keys(linkStatuses)
    .filter((k) => k === 'sensor-pipeline' || k.startsWith('sensor-pipeline:'))
    .sort()
  return [...sensor, ...RUNTIME_LINKS]
}
