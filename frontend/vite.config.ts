import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9494',
      '/socket.io': {
        target: 'http://localhost:9494',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/')
          if (!normalizedId.includes('/node_modules/')) return undefined
          if (normalizedId.includes('/node_modules/recharts/')) return 'charts'
          if (
            normalizedId.includes('/node_modules/socket.io-client/')
            || normalizedId.includes('/node_modules/engine.io-client/')
          ) return 'socket'
          if (normalizedId.includes('/node_modules/lucide-react/')) return 'icons'
          return 'vendor'
        },
      },
    },
  },
})
