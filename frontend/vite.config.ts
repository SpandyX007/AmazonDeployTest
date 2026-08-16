import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // process.env does not see .env files inside this config — loadEnv does.
  const env = loadEnv(mode, process.cwd(), '')
  const API_TARGET = env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      // Same-origin in dev, so the browser never needs a CORS preflight.
      proxy: {
        '/api': {
          target: API_TARGET,
          // Rewrite the Host header to match the target — cloud hosts
          // (App Runner, ALB host rules) route on it and 404 otherwise.
          changeOrigin: true,
        },
      },
    },
  }
})
