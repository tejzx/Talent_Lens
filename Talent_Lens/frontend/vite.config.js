import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-only proxy so `npm run dev` (port 5173) can call the FastAPI backend.
// Must match the port the backend is started on: `uvicorn server:app --port 8000`
// (this is also the port used by the Dockerfile/Procfile in production).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
