import { Moon, Sun } from 'lucide-react'
import { useTheme } from './theme'
import { cn } from '@/lib/utils'

/** Segmented light/dark switch that lives in the sidebar footer. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      <button
        type="button"
        className={cn('theme-toggle__option', theme === 'light' && 'theme-toggle__option--active')}
        aria-pressed={theme === 'light'}
        onClick={() => setTheme('light')}
      >
        <Sun aria-hidden="true" />
        Light
      </button>
      <button
        type="button"
        className={cn('theme-toggle__option', theme === 'dark' && 'theme-toggle__option--active')}
        aria-pressed={theme === 'dark'}
        onClick={() => setTheme('dark')}
      >
        <Moon aria-hidden="true" />
        Dark
      </button>
    </div>
  )
}
