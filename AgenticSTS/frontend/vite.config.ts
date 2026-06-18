import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend port — keep in sync with STS2_MONITOR_PORT (default 8081)
const BACKEND_PORT = process.env.STS2_MONITOR_PORT || '8081'
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: BACKEND_URL,
        ws: true,
      },
      '/api': {
        target: BACKEND_URL,
      },
    },
  },
})
