import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export type StatusBadgeVariant =
  | 'success' | 'warning' | 'destructive' | 'secondary' | 'default'

/** Map a link / session status to a shadcn Badge variant, preserving alarm semantics. */
export function statusBadgeVariant(state: string): StatusBadgeVariant {
  switch (state) {
    case 'up': case 'connected': case 'running': case 'active':
      return 'success'
    case 'stale': case 'connecting': case 'reconnecting':
      return 'warning'
    case 'error': case 'disabled':
      return 'destructive'
    case 'done':
      return 'default'
    default: // down / idle / disconnected / unknown
      return 'secondary'
  }
}
