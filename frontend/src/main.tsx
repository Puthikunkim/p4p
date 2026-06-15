import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/fraunces'
import '@fontsource-variable/hanken-grotesk'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
import App from './App.tsx'
import { registerRenderer, registerFallback } from './renderers/registry'
import { StatCard } from './renderers/StatCard'
import { LineChart } from './renderers/LineChart'
import { Quadrant } from './renderers/Quadrant'
import { FallbackRenderer } from './renderers/FallbackRenderer'

registerFallback(FallbackRenderer)
registerRenderer('stat_card', StatCard)
registerRenderer('line_chart', LineChart)
registerRenderer('quadrant', Quadrant)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
