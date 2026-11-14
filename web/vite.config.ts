import { defineConfig } from 'vite'

// Use the loopback release server for the APIs and packaged hazard rehearsal.
const target = process.env.RW_PLANNING_API_ORIGIN ?? 'http://127.0.0.1:8000'
const proxy = {
  '/api': { target, changeOrigin: false },
  '/healthz': { target, changeOrigin: false },
}

export default defineConfig({
  base: process.env.VITE_RELEASE_BASE ?? '/',
  server: { proxy },
  preview: { proxy },
})
