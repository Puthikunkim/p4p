import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/fraunces'
import '@fontsource-variable/hanken-grotesk'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme'
import { TooltipProvider } from './components/ui/tooltip'
import { registerRenderer, registerFallback } from './renderers/registry'
import { StatCard } from './renderers/StatCard'
import { LineChart } from './renderers/LineChart'
import { Quadrant } from './renderers/Quadrant'
import { LevelBar } from './renderers/LevelBar'
import { FallbackRenderer } from './renderers/FallbackRenderer'

registerFallback(FallbackRenderer)
registerRenderer('stat_card', StatCard)
registerRenderer('line_chart', LineChart)
registerRenderer('quadrant', Quadrant)
registerRenderer('level_bar', LevelBar)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <TooltipProvider delayDuration={200}>
        <App />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>,
)
