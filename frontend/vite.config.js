import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In dev mode, proxy API calls to the FastAPI server.
    // Production: app is served from the same origin, so relative URLs work.
    proxy: {
      '/v1': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
      '/version': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
