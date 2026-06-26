import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { RendererProps } from './registry'

export function LineChart({ channel, history }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    // uPlot renders axes/grid/ticks onto a canvas (not via CSS), so the dark theme can't
    // cascade to them — set legible colours explicitly. Series is brand lime with a soft fill.
    const axisStroke = '#7c828e'
    const gridStroke = 'rgba(255, 255, 255, 0.07)'
    const opts: uPlot.Options = {
      title: channel.display.label,
      width: containerRef.current.clientWidth || 320,
      height: 140,
      series: [
        {},
        {
          label: channel.display.label,
          stroke: '#b6f24a',
          fill: 'rgba(182, 242, 74, 0.12)',
          width: 2,
        },
      ],
      axes: [
        { label: 't (s)', stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
        { label: channel.unit, stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
      ],
      scales: channel.range
        ? { y: { range: () => [channel.range!.min, channel.range!.max] } }
        : {},
    }
    const data: uPlot.AlignedData = [[], []]
    plotRef.current = new uPlot(opts, data, containerRef.current)
    return () => {
      plotRef.current?.destroy()
      plotRef.current = null
    }
  }, [channel])  // rebuild when channel definition changes

  useEffect(() => {
    if (!plotRef.current || history.length === 0) return
    const ts = history.map(([t]) => t)
    const vals = history.map(([, v]) => v)
    plotRef.current.setData([ts, vals])
  }, [history])

  return <div ref={containerRef} className="renderer renderer--line-chart" />
}
