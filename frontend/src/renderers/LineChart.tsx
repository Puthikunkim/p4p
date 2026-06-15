import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { RendererProps } from './registry'

export function LineChart({ channel, history }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const opts: uPlot.Options = {
      title: channel.display.label,
      width: containerRef.current.clientWidth || 320,
      height: 140,
      series: [
        {},
        {
          label: channel.display.label,
          stroke: '#4338ca',
          width: 2,
        },
      ],
      axes: [
        { label: 't (s)' },
        { label: channel.unit },
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
