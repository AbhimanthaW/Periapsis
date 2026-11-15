import { defineConfig } from '@playwright/test'

declare const process: { env: { RW_UI_PRODUCTION?: string; RW_UI_API_BUNDLE?: string } }

const production = process.env.RW_UI_PRODUCTION === '1'
const port = production ? 4174 : 4173
const origin = 'http://127.0.0.1:' + port
const bundle = process.env.RW_UI_API_BUNDLE
const apiPort = 18348
const apiOrigin = 'http://127.0.0.1:' + apiPort

export default defineConfig({
  testDir: './tests',
  testMatch: ['explore.spec.ts', 'mission.spec.ts', 'hazards.spec.ts', 'objective-methods.spec.ts'],
  outputDir: './node_modules/.cache/return-window-playwright',
  use: {
    baseURL: origin,
    browserName: 'chromium',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    contextOptions: { reducedMotion: 'reduce' },
  },
  webServer: [{
    command: 'npm run ' + (production ? 'preview' : 'dev') + ' -- --host 127.0.0.1 --port ' + port + ' --strictPort',
    url: origin,
    reuseExistingServer: !bundle,
    ...(bundle && { env: { RW_PLANNING_API_ORIGIN: apiOrigin } }),
  }, ...(bundle ? [{
    cwd: '../..',
    command: 'uv run --project documentation --locked --offline python -m runtime.release serve ' + JSON.stringify(bundle) + ' --port ' + apiPort,
    url: apiOrigin + '/healthz',
  }] : [])],
})
