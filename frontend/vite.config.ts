import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Prefer proxy in Phase 0 so browser calls same-origin `/api` → backend.
      // CORS on FastAPI remains as a fallback for direct calls.
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // T-10: keep SSE `/tasks/{id}/events` from being buffered/timed out by the proxy
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
})
