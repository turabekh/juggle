import { defineConfig, devices } from '@playwright/test'

// End-to-end tests drive the real app in a browser. They expect the full stack
// to be running (they set up their own data via the API, so no specific seed is
// required):
//
//   make db && make migrate      # Postgres + schema
//   make dev                     # API  → :8000
//   make web-dev                 # web  → :9000
//   make web-e2e                 # run these tests
//
// Override targets with E2E_BASE_URL / E2E_API_URL if the stack runs elsewhere.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['line']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:9000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
