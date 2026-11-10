import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: { usePolling: true },
    proxy: {
      // changeOrigin: false conserva el Host original (localhost), que ya
      // está en ALLOWED_HOSTS de Django.
      '/api': { target: 'http://backend:8000', changeOrigin: false },
    },
  },
})
