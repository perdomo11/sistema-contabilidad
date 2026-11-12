import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, Django corre en 127.0.0.1:8000 (o en el servicio "backend" de
// docker compose si se define VITE_PROXY_TARGET). En producción, Django sirve
// el build bajo /static/ con WhiteNoise.
const destino = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
const proxy = { target: destino, changeOrigin: false, xfwd: true }

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/' : '/',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: { usePolling: true },
    proxy: {
      // changeOrigin: false conserva el Host original (localhost), que ya
      // está en ALLOWED_HOSTS de Django. xfwd agrega X-Forwarded-For para que
      // la bitácora registre la IP real del cliente.
      '/api': proxy,
      '/admin': proxy,
      '/media': proxy,
    },
  },
}))
