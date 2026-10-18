import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        // No changeOrigin: Host stays localhost:5173 so it matches the browser's Origin
        target: 'http://127.0.0.1:8000', // Points to your Python server
      }
    }
  }
})
