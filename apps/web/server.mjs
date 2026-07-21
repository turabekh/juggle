// Request-time SSR server (additive — the SPA build in dist/ is untouched).
//
//   node server.mjs                     # dev SSR (Vite middleware, on-the-fly)
//   npm run build:ssr                   # build dist/client + dist/server
//   NODE_ENV=production node server.mjs # prod SSR (serves the built bundles)
//
// It renders the app for each page request and hydrates on the client. Static
// assets and /api are left to Vite (dev) or served from dist/client (prod);
// /api itself is expected to be reverse-proxied to the FastAPI backend in prod.
//
// SSR is UNBLOCKED: the @quasar/vite-plugin `runMode: 'ssr-server'` build uses
// Quasar's SSR-safe server bundle (no `window` at import) and the app factory
// passes an ssrContext into Quasar's install — no Quasar-CLI migration needed.
// See vite.config.ts (runMode via QUASAR_SSR) and src/app.ts (ssrContext).

import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Tell vite.config to put the quasar plugin in SSR-server mode (see there).
process.env.QUASAR_SSR = 'server'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const isProd = process.env.NODE_ENV === 'production'
const port = Number(process.env.PORT || 5173)

// Serialize state safely into an inline <script> (guard the </script> sequence).
function stateScript(state) {
  if (!state || Object.keys(state).length === 0) return ''
  const json = JSON.stringify(state).replace(/</g, '\\u003c')
  return `<script>window.__PINIA__=${json}</script>`
}

function renderPage(template, appHtml, headHtml, state) {
  let html = template
    .replace('<!--ssr-outlet-->', appHtml)
    .replace('<!--ssr-state-->', stateScript(state))
  if (headHtml) {
    // The page set its own <head> — strip the static SEO defaults it supersedes
    // (avoids a duplicate <title>/robots) and inject the page-specific tags.
    html = html
      .replace(/<!--seo-defaults-start-->[\s\S]*?<!--seo-defaults-end-->/, '')
      .replace('</head>', `    ${headHtml}\n  </head>`)
  }
  return html
}

async function createDevServer() {
  const { createServer } = await import('vite')
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  return http.createServer((req, res) => {
    vite.middlewares(req, res, async () => {
      try {
        const url = req.url
        let template = fs.readFileSync(path.resolve(__dirname, 'index.html'), 'utf-8')
        template = await vite.transformIndexHtml(url, template)
        const { render } = await vite.ssrLoadModule('/src/entry-server.ts')
        const { html, head, state, status } = await render(url, req.headers)
        res.statusCode = status
        res.setHeader('Content-Type', 'text/html')
        res.end(renderPage(template, html, head, state))
      } catch (err) {
        vite.ssrFixStacktrace(err)
        console.error(err)
        res.statusCode = 500
        res.end(err.stack)
      }
    })
  })
}

const MIME = {
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain',
}

async function createProdServer() {
  const clientDir = path.resolve(__dirname, 'dist/client')
  const template = fs.readFileSync(path.resolve(clientDir, 'index.html'), 'utf-8')
  const { render } = await import('./dist/server/entry-server.js')
  return http.createServer(async (req, res) => {
    const pathname = req.url.split('?')[0]
    const filePath = path.join(clientDir, pathname)
    if (pathname !== '/' && fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      res.setHeader('Content-Type', MIME[path.extname(filePath)] ?? 'application/octet-stream')
      res.end(fs.readFileSync(filePath))
      return
    }
    try {
      const { html, head, state, status } = await render(req.url, req.headers)
      res.statusCode = status
      res.setHeader('Content-Type', 'text/html')
      res.end(renderPage(template, html, head, state))
    } catch (err) {
      console.error(err)
      res.statusCode = 500
      res.end('Internal error')
    }
  })
}

const server = isProd ? await createProdServer() : await createDevServer()
server.listen(port, () => {
  console.log(`SSR server → http://localhost:${port} (${isProd ? 'prod' : 'dev'})`)
})
