import { describe, it, expect } from 'vitest'
import { signalTimeRate } from './signalTime'

describe('signalTimeRate', () => {
  it('applies genuine small drift (rate near 1)', () => {
    // 60.5 LSL-seconds of anchors over a 60s video → ~0.8% drift, trusted.
    expect(signalTimeRate(1000, 1060.5, 60)).toBeCloseTo(60.5 / 60, 6)
  })

  it('rejects a grossly-short video and falls back to 1:1', () => {
    // Regression: real recorded session — anchors span 13.919s but the egress WebM
    // reported only 7.468s (frames truncated). r=1.86 must NOT compress the complete
    // signal data; fall back to 1:1 so all ~14s of samples still plot.
    expect(signalTimeRate(672.2, 686.119, 7.468)).toBe(1)
  })

  it('falls back to 1:1 when the stop anchor is missing', () => {
    expect(signalTimeRate(1000, null, 60)).toBe(1)
  })

  it('falls back to 1:1 when the video duration is unknown (0)', () => {
    expect(signalTimeRate(1000, 1060, 0)).toBe(1)
  })

  it('rejects an implausibly long video (rate well below 1)', () => {
    expect(signalTimeRate(1000, 1010, 60)).toBe(1)
  })
})
