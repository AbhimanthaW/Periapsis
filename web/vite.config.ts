import { defineConfig } from 'vite'

// Same-origin connection to the loopback planning service (runtime/planning_api.py).
const target = process.env.RW_PLANNING_API_ORIGIN ?? 'http://127.0.0.1:8000'
const proxy = {
  '/api': { target, changeOrigin: false },
  '/healthz': { target, changeOrigin: false },
}

export default defineConfig({
  server: { proxy },
  preview: { proxy },
})
