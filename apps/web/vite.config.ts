import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { quasar, transformAssetUrls } from '@quasar/vite-plugin'
import { defineConfig } from 'vite'

// SSR builds set QUASAR_SSR to `server` (renderToString in Node) or `client`
// (browser hydration bundle). The @quasar/vite-plugin `runMode` is the
// officially-supported SSR switch: `ssr-server` skips the client-bundle alias
// and uses Quasar's SSR-safe server build + defines __QUASAR_SSR__; `ssr-client`
// builds the hydration bundle. Unset (the default) = the plain SPA/PWA client
// build, unchanged. This is what unblocks request-time SSR without a CLI migration.
const quasarRunMode =
  process.env.QUASAR_SSR === 'server'
    ? 'ssr-server'
    : process.env.QUASAR_SSR === 'client'
      ? 'ssr-client'
      : undefined

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({
      sassVariables: fileURLToPath(new URL('./src/css/quasar.variables.scss', import.meta.url)),
      ...(quasarRunMode ? { runMode: quasarRunMode } : {}),
    }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // Bundle quasar's server build into the SSR output rather than externalising it.
  ssr: {
    noExternal: ['quasar'],
  },
  server: {
    port: 9000,
    // Proxy API calls to the FastAPI backend during dev (no CORS fuss).
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET || 'http://localhost:8000', changeOrigin: true },
    },
  },
})
