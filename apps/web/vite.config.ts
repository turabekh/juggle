import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { quasar, transformAssetUrls } from '@quasar/vite-plugin'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: fileURLToPath(new URL('./src/css/quasar.variables.scss', import.meta.url)) }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // SSR (server.mjs): load Quasar's Node/server build (its client bundle touches
  // `window` at import). Externalizing lets Node resolve the "node" export.
  ssr: {
    external: ['quasar'],
    resolve: { conditions: ['node', 'import', 'module', 'default'] },
  },
  server: {
    port: 9000,
    // Proxy API calls to the FastAPI backend during dev (no CORS fuss).
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
