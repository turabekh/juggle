import { fileURLToPath, URL } from 'node:url'

import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config'

// Reuse the app's Vite config (aliases, Vue + Quasar plugins) and layer on the
// test environment. Tests live next to the code as *.test.ts.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.{test,spec}.ts'],
      setupFiles: [fileURLToPath(new URL('./test/setup.ts', import.meta.url))],
      restoreMocks: true,
    },
  }),
)
