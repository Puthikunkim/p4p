import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { RendererProps } from './registry'
import { useTheme } from '../components/theme'

// uPlot paints axes/grid/series onto a canvas, so it can't inherit the CSS theme — colours
// are chosen per-theme here and the plot is rebuilt when the theme changes.
const CHART_THEME = {
  dark:  { axis: '#7c828e', grid: 'rgba(255, 255, 255, 0.07)', stroke: '#b6f24a', fill: 'rgba(182, 242, 74, 0.12)' },
  light: { axis: '#6b7280', grid: 'rgba(16, 24, 40, 0.10)',    stroke: '#5f8c0a', fill: 'rgba(95, 140, 10, 0.12)' },
} as const

export function LineChart({ channel, history }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const { theme } = useTheme()
  // Keep the latest history without making it a plot-rebuild trigger, so a theme rebuild
  // can re-apply the current data immediately rather than blanking the line.
  const histRef = useRef(history)
  useEffect(() => { histRef.current = history }, [history])

  useEffect(() => {
    if (!containerRef.current) return
    const c = CHART_THEME[theme]
    // window_s (Contract 1 display hint) pins the x-axis to a rolling window of the last
    // N seconds, so the visible span is fixed regardless of sample rate. Without it, uPlot
    // auto-scales x to the full data extent (the stored history, capped in the store).
    const windowS = channel.display.window_s
    const scales: uPlot.Scales = {}
    if (channel.range) {
      scales.y = { range: () => [channel.range!.min, channel.range!.max] as [number, number] }
    }
    if (windowS) {
      scales.x = { range: (_u, _min, max) => [max - windowS, max] as [number, number] }
    }
    const opts: uPlot.Options = {
      title: channel.display.label,
      width: containerRef.current.clientWidth || 320,
      height: 140,
      series: [
        {},
        {
          label: channel.display.label,
          stroke: c.stroke,
          fill: c.fill,
          width: 2,
        },
      ],
      axes: [
        { label: 't (s)', stroke: c.axis, grid: { stroke: c.grid }, ticks: { stroke: c.grid } },
        { label: channel.unit, stroke: c.axis, grid: { stroke: c.grid }, ticks: { stroke: c.grid } },
      ],
      scales,
    }
    const plot = new uPlot(opts, [[], []], containerRef.current)
    plotRef.current = plot
    const h = histRef.current
    if (h.length) plot.setData([h.map(([t]) => t), h.map(([, v]) => v)])
    return () => {
      plot.destroy()
      plotRef.current = null
    }
  }, [channel, theme])  // rebuild when the channel definition OR theme changes

  useEffect(() => {
    if (!plotRef.current || history.length === 0) return
    const ts = history.map(([t]) => t)
    const vals = history.map(([, v]) => v)
    plotRef.current.setData([ts, vals])
  }, [history])

  return <div ref={containerRef} className="renderer renderer--line-chart" />
}
