import { defineConfig } from '@playwright/test'

declare const process: { env: { RW_UI_PRODUCTION?: string } }

const production = process.env.RW_UI_PRODUCTION === '1'
const port = production ? 4174 : 4173
const origin = 'http://127.0.0.1:' + port

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
  webServer: {
    command: 'npm run ' + (production ? 'preview' : 'dev') + ' -- --host 127.0.0.1 --port ' + port + ' --strictPort',
    url: origin,
    reuseExistingServer: true,
  },
})
