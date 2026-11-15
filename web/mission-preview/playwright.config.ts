import { defineConfig } from '@playwright/test'

const origin = 'http://127.0.0.1:4173'

export default defineConfig({
  testDir: './tests',
  testMatch: ['explore.spec.ts', 'mission.spec.ts', 'hazards.spec.ts'],
  outputDir: './node_modules/.cache/return-window-playwright',
  use: {
    baseURL: origin,
    browserName: 'chromium',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    contextOptions: { reducedMotion: 'reduce' },
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173 --strictPort',
    url: origin,
    reuseExistingServer: true,
  },
})
