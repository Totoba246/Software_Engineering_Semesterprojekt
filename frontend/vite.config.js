import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs separately (uvicorn on :8000); Vite forwards /api there.
// In Docker, nginx does the same forwarding (see nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': process.env.API_URL || 'http://localhost:8000',
    },
  },
})
