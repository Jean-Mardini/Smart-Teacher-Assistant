import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const FASTAPI = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev: browser → same origin (localhost:5173) → Vite proxies to FastAPI. Avoids “can’t reach 127.0.0.1:8000”
    // when the UI is opened at http://localhost:5173 while the stack only listens on IPv4 loopback.
    proxy: {
      '/agents': { target: FASTAPI, changeOrigin: true },
      '/documents': { target: FASTAPI, changeOrigin: true },
      '/evaluation': { target: FASTAPI, changeOrigin: true },
      '/chat': { target: FASTAPI, changeOrigin: true },
      '/graph': { target: FASTAPI, changeOrigin: true },
      '/health': { target: FASTAPI, changeOrigin: true },
      '/rag': { target: FASTAPI, changeOrigin: true },
      '/generate-slides': { target: FASTAPI, changeOrigin: true },
    },
  },
})
