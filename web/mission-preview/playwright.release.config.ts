import { defineConfig } from '@playwright/test'

declare const process: { env: { RW_RELEASE_BUNDLE?: string } }

const bundle = process.env.RW_RELEASE_BUNDLE ?? 'data/offline-release'
const origin = 'http://127.0.0.1:18347'
export default defineConfig({
  testDir: './tests',
  testMatch: 'release.spec.ts',
  outputDir: './node_modules/.cache/return-window-release-playwright',
  use: { baseURL: origin, browserName: 'chromium', viewport: { width: 1440, height: 900 } },
  webServer: {
    cwd: '../..',
    command: 'uv run --project documentation --locked --offline python -m runtime.release serve ' + JSON.stringify(bundle) + ' --port 18347',
    url: origin + '/healthz',
    timeout: 30_000,
  },
})
