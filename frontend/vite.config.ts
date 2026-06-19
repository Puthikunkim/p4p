import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Dev-server proxy target. Native dev → localhost:8000; in Docker the frontend
// container reaches the backend by its compose service name (set via env).
const target = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'
const wsTarget = target.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': target,
      '/ws': {
        target: wsTarget,
        ws: true,
        configure: (proxy) => { proxy.on('error', () => {}) },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  },
})
