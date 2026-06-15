/* Line-icon set — 24×24 viewBox, inherits currentColor, 1.75 stroke.
   Kept deliberately spare to match the clinical aesthetic. */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Svg({ children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

/* Session Monitor — live waveform */
export const IconMonitor = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12h3l2.5-6 4 14 2.5-8H21" />
  </Svg>
)

/* Rule Manager — adjustable rule sliders */
export const IconRules = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12M20 18h0" />
    <circle cx="16" cy="6" r="2" />
    <circle cx="8" cy="12" r="2" />
    <circle cx="18" cy="18" r="2" />
  </Svg>
)

/* Data History — archive / past sessions */
export const IconHistory = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3.2 8.5 12 4l8.8 4.5L12 13 3.2 8.5Z" />
    <path d="M3.2 8.5V15.5L12 20l8.8-4.5V8.5" />
    <path d="M12 13v7" />
  </Svg>
)

/* System Config — pipeline / nodes */
export const IconConfig = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="6" cy="6" r="2.4" />
    <circle cx="18" cy="18" r="2.4" />
    <path d="M8.4 6H15a3 3 0 0 1 3 3v6.6M6 8.4V18" />
  </Svg>
)

export const IconPlus = (p: IconProps) => (
  <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>
)

export const IconStop = (p: IconProps) => (
  <Svg {...p}><rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none" /></Svg>
)

export const IconPause = (p: IconProps) => (
  <Svg {...p}><path d="M9 5v14M15 5v14" /></Svg>
)

export const IconPlay = (p: IconProps) => (
  <Svg {...p}><path d="M7 5.5 18 12 7 18.5V5.5Z" fill="currentColor" stroke="currentColor" strokeWidth={1.5} /></Svg>
)

export const IconWarn = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3.5 21.5 20H2.5L12 3.5Z" />
    <path d="M12 10v4.5M12 17.6v.01" />
  </Svg>
)

export const IconCheck = (p: IconProps) => (
  <Svg {...p}><path d="M4.5 12.5 9.5 17.5 19.5 6.5" /></Svg>
)

export const IconArrowLeft = (p: IconProps) => (
  <Svg {...p}><path d="M11 6 5 12l6 6M5 12h14" /></Svg>
)

/* Brand mark — concentric "core" reticle */
export const IconCore = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
    <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" />
  </Svg>
)
