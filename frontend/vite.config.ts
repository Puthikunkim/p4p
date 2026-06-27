import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// Dev-server proxy target. Native dev → localhost:8000; in Docker the frontend
// container reaches the backend by its compose service name (set via env).
const target = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'
const wsTarget = target.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
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
    // Run test files sequentially. Vitest 4's multi-worker pool intermittently races on
    // startup under CPU contention on this stack (Node 26 + Vite 8), throwing "Vitest
    // failed to find the runner". The suite is tiny, so sequential is plenty fast and
    // fully deterministic.
    fileParallelism: false,
  },
})
