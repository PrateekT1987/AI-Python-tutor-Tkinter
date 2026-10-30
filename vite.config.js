import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Development config for the browser console.
//
// The browser never sees the OpenRouter key: Vite proxies /api/openrouter to
// OpenRouter and injects the Authorization + attribution headers server-side.
// For production, build with `npm run build` and serve through `server.py`,
// which exposes the same /api/openrouter and /api/config endpoints.

function configEndpoint(model) {
  return {
    name: 'python-tutor-config',
    configureServer(server) {
      server.middlewares.use('/api/config', (_req, res) => {
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ model }))
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const baseUrl = new URL(env.OPENROUTER_BASE_URL || 'https://openrouter.ai/api/v1')
  const apiPrefix = baseUrl.pathname.replace(/\/$/, '') // e.g. /api/v1
  const apiKey = env.OPENROUTER_API_KEY || ''
  const model = env.MODEL || ''
  const referer = env.OPENROUTER_HTTP_REFERER || 'http://localhost:5173'
  const title = env.OPENROUTER_APP_TITLE || 'Python Tutor'

  return {
    plugins: [react(), configEndpoint(model)],
    server: {
      proxy: {
        '/api/openrouter': {
          target: baseUrl.origin,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/openrouter/, apiPrefix),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Authorization', `Bearer ${apiKey}`)
              proxyReq.setHeader('HTTP-Referer', referer)
              proxyReq.setHeader('X-Title', title)
            })
          },
        },
      },
    },
  }
})
