import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// Polling watcher avoids the Linux inotify `max_user_watches` ceiling
// (~65k by default — exhausted by other dev tools on the box). Polling adds
// ~1-2% idle CPU but is robust regardless of system limits. To opt out
// (after raising the kernel limit), run with VITE_POLLING=false.
const usePolling = process.env.VITE_POLLING !== 'false'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    watch: {
      usePolling,
      interval: 1000,
      // Heavy dirs we never need HMR on. Cuts watched files dramatically
      // and lowers polling CPU cost.
      ignored: [
        '**/node_modules/**',
        '**/.git/**',
        '**/dist/**',
        '../.venv/**',
        '../data/**',
        '../tests/**',
      ],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // Bypass proxy for SSE — let the browser connect directly
        bypass(req) {
          // Don't bypass non-SSE requests
          return undefined
        },
        configure: (proxy) => {
          // Disable buffering for SSE streams
          proxy.on('proxyRes', (proxyRes) => {
            const contentType = proxyRes.headers['content-type'] || ''
            if (contentType.includes('text/event-stream')) {
              // Ensure no buffering
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
    },
  },
})
