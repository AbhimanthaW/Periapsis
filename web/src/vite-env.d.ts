/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Mission site ID from src/mission/site.ts. Empty leaves the site explicitly unset. */
  readonly VITE_RW_SITE?: string
}
